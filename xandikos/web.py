# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 3
# of the License or (at your option) any later version of
# the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

"""Web server implementation..

This is the concrete web server implementation. It provides the
high level application logic that combines the WebDAV server,
the carddav support, the caldav support and the DAV store.
"""

import asyncio
import functools
import hashlib
import logging
import os
import posixpath
import shutil
import socket
import urllib.parse
from collections.abc import Iterable, Iterator
from email.utils import parseaddr
from dulwich.web import make_wsgi_chain
from dulwich.server import DictBackend
from itertools import takewhile

import jinja2

from xandikos import __version__ as xandikos_version
from xandikos import (
    access,
    apache,
    caldav,
    carddav,
    infit,
    quota,
    scheduling,
    sync,
    timezones,
    webdav,
    xmpp,
)
from xandikos.store import (
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_OTHER,
    STORE_TYPE_PRINCIPAL,
    STORE_TYPE_SCHEDULE_INBOX,
    STORE_TYPE_SCHEDULE_OUTBOX,
    STORE_TYPE_SUBSCRIPTION,
    DuplicateUidError,
    File,
    InvalidCTag,
    InvalidFileContents,
    LockedError,
    NoSuchItem,
    NotStoreError,
    OutOfSpaceError,
    Store,
)

from .icalendar import CalendarFilter, ICalendarFile
from .store.git import GitStore, TreeGitStore
from .vcard import VCardFile

logger = logging.getLogger(__name__)

try:
    import systemd.daemon
except ImportError:
    systemd_imported = False

    def get_systemd_listen_sockets() -> list[socket.socket]:
        raise NotImplementedError
else:
    systemd_imported = True

    def get_systemd_listen_sockets() -> list[socket.socket]:
        socks = []
        for fd in systemd.daemon.listen_fds():
            for family in (
                socket.AF_UNIX,  # type: ignore
                socket.AF_INET,
                socket.AF_INET6,
            ):
                if systemd.daemon.is_socket(
                    fd, family=family, type=socket.SOCK_STREAM, listening=True
                ):
                    sock = socket.fromfd(fd, family, socket.SOCK_STREAM)
                    socks.append(sock)
                    break
            else:
                raise RuntimeError(
                    "socket family must be AF_INET, AF_INET6, or AF_UNIX; "
                    "socket type must be SOCK_STREAM; and it must be listening"
                )
        return socks


try:
    from asyncio import to_thread  # type: ignore
except ImportError:  # python < 3.8
    import contextvars
    from asyncio import events

    async def to_thread(func, *args, **kwargs):  # type: ignore
        loop = events.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)


WELLKNOWN_DAV_PATHS = {
    caldav.WELLKNOWN_CALDAV_PATH,
    carddav.WELLKNOWN_CARDDAV_PATH,
}

STORE_CACHE_SIZE = 128
# TODO(jelmer): Make these configurable/dynamic
CALENDAR_HOME_SET = ["calendars"]
ADDRESSBOOK_HOME_SET = ["contacts"]
GIT_PATH = ".git"

# Mapping from content types to their validation error tags
CONTENT_TYPE_ERROR_TAGS = {
    "text/calendar": ("{%s}valid-calendar-data" % caldav.NAMESPACE, "calendar"),
    "text/vcard": ("{%s}valid-address-data" % carddav.NAMESPACE, "vCard"),
}


def get_validation_error(exc: InvalidFileContents):
    """Get appropriate validation error tag for a content type.

    Args:
        exc: InvalidFileContents exception with content_type and error details

    Returns:
        Tuple of (error_tag, error_message) for the content type
    """
    error_tag, file_type = CONTENT_TYPE_ERROR_TAGS.get(
        exc.content_type,
        ("{%s}valid-calendar-data" % caldav.NAMESPACE, "file"),
    )
    return error_tag, f"Not a valid {file_type} file: {exc.error}"


TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR), enable_async=True
)


async def render_jinja_page(
    name: str, accepted_content_languages: list[str], **kwargs
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render a HTML page from jinja template.

    Args:
      name: Name of the page
      accepted_content_languages: List of accepted content languages
    Returns: Tuple of (body, content_length, etag, content_type, languages)
    """
    # TODO(jelmer): Support rendering other languages
    encoding = "utf-8"
    template = jinja_env.get_template(name)
    body = await template.render_async(
        version=xandikos_version, urljoin=urllib.parse.urljoin, **kwargs
    )
    body_encoded = body.encode(encoding)
    return (
        [body_encoded],
        len(body_encoded),
        None,
        f"text/html; encoding={encoding}",
        ["en-UK"],
    )


def create_strong_etag(etag: str) -> str:
    """Create strong etags.

    Args:
      etag: basic etag
    Returns: A strong etag
    """
    return '"' + etag + '"'


def extract_strong_etag(etag: str | None) -> str | None:
    """Extract a strong etag from a string."""
    if etag is None:
        return etag
    return etag.strip('"')


class ObjectResource(webdav.Resource):
    """Object resource."""

    def __init__(
        self,
        store: Store,
        name: str,
        content_type: str,
        etag: str,
        file: File | None = None,
    ) -> None:
        self.store = store
        self.name = name
        self.etag = etag
        self.content_type = content_type
        self._file = file

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.store!r}, {self.name!r}, {self.etag!r}, {self.get_content_type()!r})"

    async def get_file(self) -> File:
        if self._file is None:
            self._file = await to_thread(
                self.store.get_file, self.name, self.content_type, self.etag
            )
            assert self._file is not None
        return self._file

    async def get_body(self) -> Iterable[bytes]:
        file = await self.get_file()
        return file.content

    async def set_body(self, data, replace_etag=None):
        try:
            (name, etag) = await to_thread(
                self.store.import_one,
                self.name,
                self.content_type,
                data,
                replace_etag=extract_strong_etag(replace_etag),
            )
        except InvalidFileContents as exc:
            error_tag, error_message = get_validation_error(exc)
            raise webdav.PreconditionFailure(error_tag, error_message) from exc
        except DuplicateUidError as exc:
            raise webdav.PreconditionFailure(
                "{%s}no-uid-conflict" % caldav.NAMESPACE, "UID already in use."
            ) from exc
        except LockedError as exc:
            raise webdav.ResourceLocked() from exc
        return create_strong_etag(etag)

    def get_content_language(self) -> str:
        raise KeyError

    def get_content_type(self) -> str:
        return self.content_type

    async def get_content_length(self) -> int:
        return sum(map(len, await self.get_body()))

    async def get_etag(self) -> str:
        return create_strong_etag(self.etag)

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def get_owner(self):
        return None

    def get_comment(self):
        raise KeyError

    def set_comment(self, comment):
        raise NotImplementedError(self.set_comment)

    def get_creationdate(self):
        # TODO(jelmer): Find creation date using store function
        raise KeyError

    def get_last_modified(self):
        # TODO(jelmer): Find last modified time using store function
        raise KeyError

    def get_is_executable(self):
        # TODO(jelmer): Retrieve POSIX mode and check for executability.
        return False

    def get_quota_used_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_quota_available_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_schedule_tag(self):
        # TODO(jelmer): Ask the store?
        raise KeyError


class StoreBasedCollection:
    def __init__(self, backend, relpath, store) -> None:
        self.backend = backend
        self.relpath = relpath
        self.store = store

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.store!r})"

    def set_resource_types(self, resource_types):
        # TODO(jelmer): Allow more than just this set; allow combining
        # addressbook/calendar.
        resource_types = set(resource_types)
        if resource_types == {
            caldav.CALENDAR_RESOURCE_TYPE,
            webdav.COLLECTION_RESOURCE_TYPE,
        }:
            self.store.set_type(STORE_TYPE_CALENDAR)
        elif resource_types == {
            carddav.ADDRESSBOOK_RESOURCE_TYPE,
            webdav.COLLECTION_RESOURCE_TYPE,
        }:
            self.store.set_type(STORE_TYPE_ADDRESSBOOK)
        elif resource_types == {webdav.PRINCIPAL_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_PRINCIPAL)
        elif resource_types == {
            caldav.SCHEDULE_INBOX_RESOURCE_TYPE,
            webdav.COLLECTION_RESOURCE_TYPE,
        }:
            self.store.set_type(STORE_TYPE_SCHEDULE_INBOX)
        elif resource_types == {
            caldav.SCHEDULE_OUTBOX_RESOURCE_TYPE,
            webdav.COLLECTION_RESOURCE_TYPE,
        }:
            self.store.set_type(STORE_TYPE_SCHEDULE_OUTBOX)
        elif resource_types == {webdav.COLLECTION_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_OTHER)
        elif resource_types == {
            webdav.COLLECTION_RESOURCE_TYPE,
            caldav.SUBSCRIPTION_RESOURCE_TYPE,
        }:
            self.store.set_type(STORE_TYPE_SUBSCRIPTION)
        else:
            raise NotImplementedError(self.set_resource_types)

    def _get_resource(
        self,
        name: str,
        content_type: str,
        etag: str,
        file: File | None = None,
    ) -> webdav.Resource:
        return ObjectResource(self.store, name, content_type, etag, file=file)

    def _get_subcollection(self, name: str) -> webdav.Collection:
        return self.backend.get_resource(posixpath.join(self.relpath, name))

    def get_displayname(self) -> str:
        displayname = self.store.get_displayname()
        if displayname is None:
            return os.path.basename(self.store.repo.path)
        return displayname

    def set_displayname(self, displayname: str) -> None:
        self.store.set_displayname(displayname)

    def get_sync_token(self) -> str:
        return self.store.get_ctag()

    def get_ctag(self) -> str:
        return self.store.get_ctag()

    async def get_etag(self) -> str:
        return create_strong_etag(self.store.get_ctag())

    def members(self) -> Iterator[tuple[str, webdav.Resource]]:
        for name, content_type, etag in self.store.iter_with_etag():
            resource = self._get_resource(name, content_type, etag)
            yield (name, resource)
        for name, resource in self.subcollections():
            yield (name, resource)

    def subcollections(self):
        for name in self.store.subdirectories():
            yield (name, self._get_subcollection(name))

    def get_member(self, name):
        assert name != ""
        for fname, content_type, fetag in self.store.iter_with_etag():
            if name == fname:
                return self._get_resource(name, content_type, fetag)
        if name in self.store.subdirectories():
            return self._get_subcollection(name)
        raise KeyError(name)

    def delete_member(self, name, etag=None):
        assert name != ""
        try:
            self.store.delete_one(name, etag=extract_strong_etag(etag))
        except NoSuchItem:
            try:
                _subcoll = self._get_subcollection(name)
            except KeyError:
                # Item doesn't exist at all, raise KeyError to return 404
                raise KeyError(name)
            else:
                # TODO: Properly allow removing subcollections
                # _subcoll.destroy()
                shutil.rmtree(os.path.join(self.store.path, name))

    async def create_member(
        self,
        name: str,
        contents: Iterable[bytes],
        content_type: str,
        requester: str | None = None,
    ) -> tuple[str, str]:
        # Check if member already exists and raise FileExistsError if it does
        try:
            existing_member = self.get_member(name)
            if existing_member is not None:
                raise FileExistsError(f"Member '{name}' already exists")
        except KeyError:
            # Member doesn't exist, which is what we want for create_member
            pass

        try:
            (name, etag) = self.store.import_one(
                name, content_type, contents, requester=requester
            )
        except InvalidFileContents as exc:
            error_tag, error_message = get_validation_error(exc)
            raise webdav.PreconditionFailure(error_tag, error_message) from exc
        except DuplicateUidError as exc:
            raise webdav.PreconditionFailure(
                "{%s}no-uid-conflict" % caldav.NAMESPACE, "UID already in use."
            ) from exc
        except OutOfSpaceError as exc:
            raise webdav.InsufficientStorage() from exc
        except LockedError as exc:
            raise webdav.ResourceLocked() from exc
        return (name, create_strong_etag(etag))

    def iter_differences_since(
        self, old_token: str, new_token: str
    ) -> Iterator[tuple[str, webdav.Resource | None, webdav.Resource | None]]:
        old_resource: webdav.Resource | None
        new_resource: webdav.Resource | None
        try:
            for (
                name,
                content_type,
                old_etag,
                new_etag,
            ) in self.store.iter_changes(old_token, new_token):
                if old_etag is not None:
                    old_resource = self._get_resource(name, content_type, old_etag)
                else:
                    old_resource = None
                if new_etag is not None:
                    new_resource = self._get_resource(name, content_type, new_etag)
                else:
                    new_resource = None
                yield (name, old_resource, new_resource)
        except InvalidCTag as exc:
            raise sync.InvalidToken(exc.ctag) from exc

    def get_owner(self):
        return None

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def get_headervalue(self):
        raise KeyError

    def get_comment(self):
        return self.store.get_comment()

    def set_comment(self, comment):
        self.store.set_comment(comment)

    def get_creationdate(self):
        # TODO(jelmer): Find creation date using store function
        raise KeyError

    def get_last_modified(self):
        # TODO(jelmer): Find last modified time using store function
        raise KeyError

    def get_content_type(self):
        return "httpd/unix-directory"

    def get_content_language(self):
        raise KeyError

    async def get_content_length(self):
        raise KeyError

    def destroy(self) -> None:
        # RFC2518, section 8.6.2 says this should recursively delete.
        self.store.destroy()

    async def get_body(self):
        raise NotImplementedError(self.get_body)

    async def render(
        self, self_url, accepted_content_types, accepted_content_languages
    ):
        content_types = webdav.pick_content_types(accepted_content_types, ["text/html"])
        assert content_types == ["text/html"]
        return await render_jinja_page(
            "collection.html",
            accepted_content_languages,
            collection=self,
            self_url=self_url,
        )

    def get_is_executable(self) -> bool:
        return False

    def get_quota_used_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_quota_available_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_refreshrate(self):
        return self.store.config.get_refreshrate()

    def set_refreshrate(self, value):
        self.store.config.set_refreshrate(value)


class Collection(StoreBasedCollection, webdav.Collection):
    """A generic WebDAV collection."""


class ScheduleInbox(StoreBasedCollection, scheduling.ScheduleInbox):
    """A schedling inbox collection."""


class ScheduleOutbox(StoreBasedCollection, scheduling.ScheduleOutbox):
    """A schedling outbox collection."""


class SubscriptionCollection(StoreBasedCollection, caldav.Subscription):
    def get_source_url(self):
        source_url = self.store.get_source_url()
        if source_url is None:
            raise KeyError
        return source_url

    def set_source_url(self, url):
        self.store.set_source_url(url)

    def get_calendar_description(self):
        return self.store.get_description()

    def get_calendar_color(self):
        color = self.store.get_color()
        if not color:
            raise KeyError
        if color and color[0] != "#":
            color = "#" + color
        return color

    def set_calendar_color(self, color):
        self.store.set_color(color)

    def get_supported_calendar_components(self):
        return ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY"]


class CalendarCollection(StoreBasedCollection, caldav.Calendar):
    def get_calendar_description(self):
        return self.store.get_description()

    def set_calendar_description(self, description):
        self.store.set_description(description)

    def get_calendar_color(self):
        color = self.store.get_color()
        if not color:
            raise KeyError
        if color and color[0] != "#":
            color = "#" + color
        return color

    def set_calendar_color(self, color):
        self.store.set_color(color)

    def get_calendar_order(self):
        order = self.store.config.get_order()
        if not order:
            raise KeyError
        return order

    def set_calendar_order(self, order):
        self.store.config.set_order(order)

    def get_calendar_timezone(self):
        return self.store.config.get_timezone()

    def set_calendar_timezone(self, content):
        self.store.config.set_timezone(content)

    def _ensure_metadata_directory(self):
        """Ensure .xandikos/ metadata directory exists, migrating from old .xandikos config file if needed."""
        # Check if we already have the new directory structure by checking for config file
        try:
            self.store.get_file(".xandikos/config", "text/plain")
            return  # Already migrated
        except KeyError:
            pass  # Need to migrate or create

        # Check if we have the old .xandikos file that needs migration
        old_config_content = None
        try:
            old_config_file = self.store.get_file(".xandikos", "text/plain")
        except KeyError:
            pass  # No old config file to migrate
        else:
            old_config_content = b"".join(old_config_file.content)
            # Remove the old file
            self.store.delete_one(".xandikos")

        # Create .xandikos/ metadata directory by creating config file within it
        if old_config_content:
            # Migrate old config file content
            content = [old_config_content]
            message = "Migrate .xandikos config to metadata directory structure"
        else:
            # Create empty config file to establish the metadata directory
            content = [b""]
            message = "Create .xandikos metadata directory structure"

        self.store.import_one(
            ".xandikos/config", "text/plain", content, message=message
        )

    def get_calendar_availability(self):
        """Get calendar availability from .xandikos/availability.ics file."""
        try:
            availability_file = self.store.get_file(
                ".xandikos/availability.ics", "text/calendar"
            )
        except NoSuchItem:
            raise KeyError

        return b"".join(availability_file.content).decode("utf-8")

    def set_calendar_availability(self, content):
        """Set calendar availability by storing in .xandikos/availability.ics file."""
        # Ensure .xandikos/ metadata directory exists (migrates config if needed)
        self._ensure_metadata_directory()

        if content is None:
            # Remove availability
            try:
                self.store.delete_one(".xandikos/availability.ics")
            except NoSuchItem:
                pass  # Already removed
        else:
            # Validate that it's valid iCalendar data and normalize it
            try:
                from icalendar.cal import Calendar as ICalendar

                cal = ICalendar.from_ical(content)
            except (ValueError, UnicodeDecodeError, TypeError, KeyError) as e:
                raise InvalidFileContents("text/calendar", content, e)

            # Store the normalized form
            normalized_content = cal.to_ical().decode("utf-8")
            self.store.import_one(
                ".xandikos/availability.ics",
                "text/calendar",
                [normalized_content.encode("utf-8")],
                message="Update calendar availability",
            )

    def get_supported_calendar_components(self):
        return ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY"]

    def get_supported_calendar_data_types(self):
        return [("text/calendar", "1.0"), ("text/calendar", "2.0")]

    def get_max_date_time(self):
        return "99991231T235959Z"

    def get_min_date_time(self):
        return "00010101T000000Z"

    def get_max_instances(self):
        raise KeyError

    def get_max_attendees_per_instance(self):
        raise KeyError

    def get_max_resource_size(self):
        # No resource limit
        raise KeyError

    def get_max_attachments_per_resource(self):
        # No resource limit
        raise KeyError

    def get_max_attachment_size(self):
        # No resource limit
        raise KeyError

    def get_schedule_calendar_transparency(self):
        # TODO(jelmer): Allow configuration in config
        return caldav.TRANSPARENCY_OPAQUE

    def get_managed_attachments_server_url(self):
        # TODO(jelmer)
        raise KeyError

    def calendar_query(self, create_filter_fn):
        filter = create_filter_fn(CalendarFilter)
        for name, file, etag in self.store.iter_with_filter(filter=filter):
            resource = self._get_resource(name, file.content_type, etag, file=file)
            yield (name, resource)

    def get_xmpp_heartbeat(self):
        # TODO
        raise KeyError

    def get_xmpp_server(self):
        # TODO
        raise KeyError

    def get_xmpp_uri(self):
        # TODO
        raise KeyError


class AddressbookCollection(StoreBasedCollection, carddav.Addressbook):
    def get_addressbook_description(self):
        return self.store.get_description()

    def set_addressbook_description(self, description):
        self.store.set_description(description)

    def get_supported_address_data_types(self):
        return [("text/vcard", "3.0")]

    def get_max_resource_size(self):
        # No resource limit
        raise KeyError

    def get_max_image_size(self):
        # No resource limit
        raise KeyError

    def set_addressbook_color(self, color):
        self.store.set_color(color)

    def addressbook_query(self, create_filter_fn):
        from .vcard import CardDAVFilter

        filter = create_filter_fn(CardDAVFilter)
        for name, file, etag in self.store.iter_with_filter(filter=filter):
            resource = self._get_resource(name, file.content_type, etag, file=file)
            yield (name, resource)

    def get_addressbook_color(self):
        color = self.store.get_color()
        if not color:
            raise KeyError
        if color and color[0] != "#":
            color = "#" + color
        return color


class CollectionSetResource(webdav.Collection):
    """Resource for calendar sets."""

    def __init__(self, backend, relpath) -> None:
        self.backend = backend
        self.relpath = relpath

    @classmethod
    def create(cls, backend, relpath):
        path = backend._map_to_file_path(relpath)
        if not os.path.isdir(path):
            os.makedirs(path)
            logging.info("Creating %s", path)
        return cls(backend, relpath)

    def get_displayname(self):
        return posixpath.basename(self.relpath)

    def get_sync_token(self):
        raise KeyError

    async def get_etag(self):
        raise KeyError

    def get_ctag(self):
        raise KeyError

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def get_owner(self):
        return None

    def members(self):
        p = self.backend._map_to_file_path(self.relpath)
        for name in os.listdir(p):
            if name.startswith("."):
                continue
            resource = self.get_member(name)
            yield (name, resource)

    def get_member(self, name):
        assert name != ""
        relpath = posixpath.join(self.relpath, name)
        p = self.backend._map_to_file_path(relpath)
        if not os.path.isdir(p):
            raise KeyError(name)
        return self.backend.get_resource(relpath)

    def get_headervalue(self):
        raise KeyError

    def get_comment(self):
        raise KeyError

    def set_comment(self, comment):
        raise NotImplementedError(self.set_comment)

    def get_content_type(self):
        return "httpd/unix-directory"

    def get_content_language(self):
        raise KeyError

    async def get_content_length(self):
        raise KeyError

    def get_last_modified(self):
        # TODO(jelmer): Find last modified time using store function
        raise KeyError

    def delete_member(self, name, etag=None):
        # This doesn't have any non-collection members.
        self.get_member(name).destroy()

    def destroy(self):
        p = self.backend._map_to_file_path(self.relpath)
        # RFC2518, section 8.6.2 says this should recursively delete.
        shutil.rmtree(p)

    async def render(
        self, self_url, accepted_content_types, accepted_content_languages
    ):
        content_types = webdav.pick_content_types(accepted_content_types, ["text/html"])
        assert content_types == ["text/html"]
        return await render_jinja_page(
            "root.html", accepted_content_languages, self_url=self_url
        )

    def get_is_executable(self):
        return False

    def get_quota_used_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_quota_available_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_creationdate(self):
        # TODO(jelmer): Find creation date using store function
        raise KeyError


class RootPage(webdav.Resource):
    """A non-DAV resource."""

    resource_types: list[str] = []

    def __init__(self, backend) -> None:
        self.backend = backend

    def render(self, self_url, accepted_content_types, accepted_content_languages):
        content_types = webdav.pick_content_types(accepted_content_types, ["text/html"])
        assert content_types == ["text/html"]

        # Generate CalDAV/CardDAV URLs
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(self_url)

        # Determine if we're using HTTPS
        is_secure = parsed.scheme == "https"

        # Create URLs with different schemes, preserving the full path
        caldav_url = urlunparse(
            (
                "caldavs" if is_secure else "caldav",
                parsed.netloc,
                parsed.path,
                "",
                "",
                "",
            )
        )
        carddav_url = urlunparse(
            (
                "carddavs" if is_secure else "carddav",
                parsed.netloc,
                parsed.path,
                "",
                "",
                "",
            )
        )

        # Generate DAV×5 URL for QR code
        davx5_url = urlunparse(("davx5", parsed.netloc, parsed.path, "", "", ""))

        # Try to generate QR code if qrcode is available
        qr_code_data = None
        try:
            import qrcode
        except ImportError:
            logger.warning("qrcode package not installed; QR code generation disabled")
        else:
            import io
            import base64

            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(davx5_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_code_data = base64.b64encode(buffer.getvalue()).decode()

        return render_jinja_page(
            "root.html",
            accepted_content_languages,
            principals=self.backend.find_principals(),
            self_url=self_url,
            caldav_url=caldav_url,
            carddav_url=carddav_url,
            davx5_url=davx5_url,
            qr_code_data=qr_code_data,
        )

    async def get_body(self):
        raise KeyError

    async def get_content_length(self):
        raise KeyError

    def get_content_type(self):
        return "text/html"

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    async def get_etag(self):
        h = hashlib.md5()
        for c in await self.get_body():
            h.update(c)
        return h.hexdigest()

    def get_last_modified(self):
        raise KeyError

    def get_content_language(self):
        return ["en-UK"]

    def get_member(self, name):
        return self.backend.get_resource("/" + name)

    def delete_member(self, name, etag=None):
        # This doesn't have any non-collection members.
        self.get_member("/" + name).destroy()

    def get_is_executable(self):
        return False

    def get_quota_used_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_quota_available_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError


class Principal(webdav.Principal):
    def get_principal_url(self):
        return "."

    def get_principal_address(self):
        raise KeyError

    def get_calendar_home_set(self):
        return CALENDAR_HOME_SET

    def get_addressbook_home_set(self):
        return ADDRESSBOOK_HOME_SET

    def get_calendar_user_address_set(self):
        # TODO(jelmer): Make this configurable
        ret = []
        try:
            (fullname, email) = parseaddr(os.environ["EMAIL"])
        except KeyError:
            pass
        else:
            ret.append("mailto:" + email)
        return ret

    def set_infit_settings(self, settings):
        relpath = posixpath.join(self.relpath, ".infit")
        p = self.backend._map_to_file_path(relpath)
        with open(p, "w") as f:
            f.write(settings)

    def get_infit_settings(self):
        relpath = posixpath.join(self.relpath, ".infit")
        p = self.backend._map_to_file_path(relpath)
        if not os.path.exists(p):
            raise KeyError
        with open(p) as f:
            return f.read()

    def get_group_membership(self):
        """Get group membership URLs."""
        return []

    def get_calendar_user_type(self):
        # TODO(jelmer)
        return scheduling.CALENDAR_USER_TYPE_INDIVIDUAL

    def get_calendar_proxy_read_for(self):
        # TODO(jelmer)
        return []

    def get_calendar_proxy_write_for(self):
        # TODO(jelmer)
        return []

    def get_owner(self):
        return None

    def get_schedule_outbox_url(self):
        raise KeyError

    def get_schedule_inbox_url(self):
        # TODO(jelmer): make this configurable
        return "inbox"

    def get_creationdate(self):
        raise KeyError


class PrincipalBare(CollectionSetResource, Principal):
    """Principal user resource."""

    resource_types = [webdav.PRINCIPAL_RESOURCE_TYPE]

    @classmethod
    def create(cls, backend, relpath):
        p = super().create(backend, relpath)
        to_create = set()
        to_create.update(p.get_addressbook_home_set())
        to_create.update(p.get_calendar_home_set())
        for n in to_create:
            try:
                backend.create_collection(posixpath.join(relpath, n))
            except FileExistsError:
                pass
        return p

    async def render(
        self, self_url, accepted_content_types, accepted_content_languages
    ):
        content_types = webdav.pick_content_types(accepted_content_types, ["text/html"])
        assert content_types == ["text/html"]
        return await render_jinja_page(
            "principal.html",
            accepted_content_languages,
            principal=self,
            self_url=self_url,
        )

    def subcollections(self):
        # TODO(jelmer): Return members
        return []


class PrincipalCollection(Collection, Principal):
    """Principal user resource."""

    resource_types = webdav.Collection.resource_types + [webdav.PRINCIPAL_RESOURCE_TYPE]

    @classmethod
    def create(cls, backend, relpath):
        p = super().create(backend, relpath)
        p.store.set_type(STORE_TYPE_PRINCIPAL)
        to_create = set()
        to_create.update(p.get_addressbook_home_set())
        to_create.update(p.get_calendar_home_set())
        for n in to_create:
            try:
                backend.create_collection(posixpath.join(relpath, n))
            except FileExistsError:
                pass
        return p


@functools.lru_cache(maxsize=STORE_CACHE_SIZE)
def open_store_from_path(path: str, **kwargs):
    store = GitStore.open_from_path(path, **kwargs)
    store.load_extra_file_handler(ICalendarFile)
    store.load_extra_file_handler(VCardFile)
    return store


class XandikosBackend(webdav.Backend):
    def __init__(
        self, path, *, paranoid: bool = False, index_threshold: int | None = None
    ) -> None:
        self.path = path
        self._user_principals: set[str] = set()
        self.paranoid = paranoid
        self.index_threshold = index_threshold

    def _map_to_file_path(self, relpath):
        return os.path.join(self.path, relpath.lstrip("/"))

    def _mark_as_principal(self, path):
        self._user_principals.add(posixpath.normpath(path))

    def create_collection(self, relpath):
        p = self._map_to_file_path(relpath)
        return Collection(self, relpath, TreeGitStore.create(p))

    def create_principal(self, relpath, create_defaults=False):
        principal = PrincipalBare.create(self, relpath)
        self._mark_as_principal(relpath)
        if create_defaults:
            create_principal_defaults(self, principal)

    def find_principals(self):
        """List all of the principals on this server."""
        return self._user_principals

    def get_resource(self, relpath):
        relpath = posixpath.normpath(relpath)
        if not relpath.startswith("/"):
            raise ValueError("relpath %r should start with /")
        if relpath == "/":
            return RootPage(self)
        p = self._map_to_file_path(relpath)
        if p is None:
            return None
        if os.path.isdir(p):
            try:
                store = open_store_from_path(
                    p,
                    double_check_indexes=self.paranoid,
                    index_threshold=self.index_threshold,
                )
            except NotStoreError:
                if relpath in self._user_principals:
                    return PrincipalBare(self, relpath)
                return CollectionSetResource(self, relpath)
            else:
                return {
                    STORE_TYPE_CALENDAR: CalendarCollection,
                    STORE_TYPE_ADDRESSBOOK: AddressbookCollection,
                    STORE_TYPE_PRINCIPAL: PrincipalCollection,
                    STORE_TYPE_SCHEDULE_INBOX: ScheduleInbox,
                    STORE_TYPE_SCHEDULE_OUTBOX: ScheduleOutbox,
                    STORE_TYPE_SUBSCRIPTION: SubscriptionCollection,
                    STORE_TYPE_OTHER: Collection,
                }[store.get_type()](self, relpath, store)
        else:
            (basepath, name) = os.path.split(relpath)
            assert name != "", f"path is {relpath!r}"
            store = self.get_resource(basepath)
            if store is None:
                return None
            if webdav.COLLECTION_RESOURCE_TYPE not in store.resource_types:
                return None
            try:
                return store.get_member(name)
            except KeyError:
                return None

    async def copy_collection(
        self, source_path: str, dest_path: str, overwrite: bool = True
    ) -> bool:
        """Copy a collection recursively."""
        import shutil

        source_collection = self.get_resource(source_path)
        if source_collection is None:
            raise KeyError(source_path)

        if webdav.COLLECTION_RESOURCE_TYPE not in source_collection.resource_types:
            raise ValueError(f"Source '{source_path}' is not a collection")

        source_file_path = self._map_to_file_path(source_path)
        dest_file_path = self._map_to_file_path(dest_path)

        # Check if destination exists
        did_overwrite = False
        if os.path.exists(dest_file_path):
            if not overwrite:
                raise FileExistsError(f"Collection '{dest_path}' already exists")
            # Remove existing destination (file or directory)
            did_overwrite = True
            if os.path.isdir(dest_file_path):
                shutil.rmtree(dest_file_path)
            else:
                os.remove(dest_file_path)

        # Copy the entire directory tree
        shutil.copytree(source_file_path, dest_file_path)
        return did_overwrite

    async def move_collection(
        self, source_path: str, dest_path: str, overwrite: bool = True
    ) -> bool:
        """Move a collection recursively."""
        import shutil

        source_collection = self.get_resource(source_path)
        if source_collection is None:
            raise KeyError(source_path)

        if webdav.COLLECTION_RESOURCE_TYPE not in source_collection.resource_types:
            raise ValueError(f"Source '{source_path}' is not a collection")

        source_file_path = self._map_to_file_path(source_path)
        dest_file_path = self._map_to_file_path(dest_path)

        # Check if destination exists
        did_overwrite = False
        if os.path.exists(dest_file_path):
            if not overwrite:
                raise FileExistsError(f"Collection '{dest_path}' already exists")
            did_overwrite = True
            # Remove existing destination (file or directory)
            if os.path.isdir(dest_file_path):
                shutil.rmtree(dest_file_path)
            else:
                os.remove(dest_file_path)

        # Move the entire directory tree
        shutil.move(source_file_path, dest_file_path)
        return did_overwrite


class XandikosApp(webdav.WebDAVApp):
    """A wsgi App that provides a Xandikos web server."""

    def __init__(self, backend, current_user_principal, strict=True) -> None:
        super().__init__(backend, strict=strict)

        def get_current_user_principal(env):
            try:
                return current_user_principal % env
            except KeyError:
                return None

        self.register_properties(
            [
                webdav.ResourceTypeProperty(),
                webdav.CurrentUserPrincipalProperty(get_current_user_principal),
                webdav.PrincipalURLProperty(),
                webdav.DisplayNameProperty(),
                webdav.GetETagProperty(),
                webdav.GetContentTypeProperty(),
                webdav.GetContentLengthProperty(),
                webdav.GetContentLanguageProperty(),
                caldav.SourceProperty(),
                caldav.CalendarHomeSetProperty(),
                carddav.AddressbookHomeSetProperty(),
                caldav.CalendarDescriptionProperty(),
                caldav.CalendarColorProperty(),
                caldav.CalendarOrderProperty(),
                caldav.CreatedByProperty(),
                caldav.UpdatedByProperty(),
                caldav.SupportedCalendarComponentSetProperty(),
                carddav.AddressbookDescriptionProperty(),
                carddav.PrincipalAddressProperty(),
                webdav.AppleGetCTagProperty(),
                webdav.DAVGetCTagProperty(),
                carddav.SupportedAddressDataProperty(),
                webdav.SupportedReportSetProperty(self.reporters),
                sync.SyncTokenProperty(),
                caldav.SupportedCalendarDataProperty(),
                caldav.CalendarTimezoneProperty(),
                caldav.CalendarAvailabilityProperty(),
                caldav.MinDateTimeProperty(),
                caldav.MaxDateTimeProperty(),
                caldav.MaxResourceSizeProperty(),
                carddav.MaxResourceSizeProperty(),
                carddav.MaxImageSizeProperty(),
                access.CurrentUserPrivilegeSetProperty(),
                access.OwnerProperty(),
                webdav.CreationDateProperty(),
                webdav.SupportedLockProperty(),
                webdav.LockDiscoveryProperty(),
                infit.AddressbookColorProperty(),
                infit.SettingsProperty(),
                infit.HeaderValueProperty(),
                webdav.CommentProperty(),
                scheduling.CalendarUserAddressSetProperty(),
                scheduling.ScheduleInboxURLProperty(),
                scheduling.ScheduleOutboxURLProperty(),
                scheduling.CalendarUserTypeProperty(),
                scheduling.ScheduleTagProperty(),
                webdav.GetLastModifiedProperty(),
                timezones.TimezoneServiceSetProperty([]),
                webdav.AddMemberProperty(),
                caldav.ScheduleCalendarTransparencyProperty(),
                scheduling.ScheduleDefaultCalendarURLProperty(),
                caldav.MaxInstancesProperty(),
                caldav.MaxAttendeesPerInstanceProperty(),
                access.GroupMembershipProperty(),
                apache.ExecutableProperty(),
                caldav.CalendarProxyReadForProperty(),
                caldav.CalendarProxyWriteForProperty(),
                caldav.MaxAttachmentSizeProperty(),
                caldav.MaxAttachmentsPerResourceProperty(),
                caldav.ManagedAttachmentsServerURLProperty(),
                quota.QuotaAvailableBytesProperty(),
                quota.QuotaUsedBytesProperty(),
                webdav.RefreshRateProperty(),
                xmpp.XmppUriProperty(),
                xmpp.XmppServerProperty(),
                xmpp.XmppHeartbeatProperty(),
            ]
        )
        self.register_reporters(
            [
                caldav.CalendarMultiGetReporter(),
                caldav.CalendarQueryReporter(),
                carddav.AddressbookMultiGetReporter(),
                carddav.AddressbookQueryReporter(),
                webdav.ExpandPropertyReporter(),
                sync.SyncCollectionReporter(),
                caldav.FreeBusyQueryReporter(),
            ]
        )
        self.register_methods(
            [
                caldav.MkcalendarMethod(),
            ]
        )

    async def _handle_request(self, request, environ, start_response=None):
        if start_response and GIT_PATH in request.path.split(posixpath.sep):
            return self._handle_git_request(
                request,
                environ["ORIGINAL_ENVIRON"],
                takewhile(lambda x: x != GIT_PATH, request.path.split(posixpath.sep)),
                start_response,
            )
        else:
            return await super()._handle_request(request, environ)

    def _handle_git_request(self, request, environ, path, start_response):
        resource_path = posixpath.join("/", *path)
        resource = self.backend.get_resource(resource_path)
        if not isinstance(resource, StoreBasedCollection) or not isinstance(
            resource.store, GitStore
        ):
            return webdav._send_not_found(request)

        prefix = posixpath.join(resource_path, GIT_PATH)
        chain = make_wsgi_chain(DictBackend({prefix: resource.store.repo}), dumb=True)
        return chain(environ, start_response)


def create_principal_defaults(backend, principal):
    """Create default calendar and addressbook for a principal.

    Args:
      backend: Backend in which the principal exists.
      principal: Principal object
    """
    calendar_path = posixpath.join(
        principal.relpath, principal.get_calendar_home_set()[0], "calendar"
    )
    try:
        resource = backend.create_collection(calendar_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_CALENDAR)
        logging.info("Create calendar in %s.", resource.store.path)
    addressbook_path = posixpath.join(
        principal.relpath,
        principal.get_addressbook_home_set()[0],
        "addressbook",
    )
    try:
        resource = backend.create_collection(addressbook_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_ADDRESSBOOK)
        logging.info("Create addressbook in %s.", resource.store.path)
    calendar_path = posixpath.join(
        principal.relpath, principal.get_schedule_inbox_url()
    )
    try:
        resource = backend.create_collection(calendar_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_SCHEDULE_INBOX)
        logging.info("Create inbox in %s.", resource.store.path)


class RedirectDavHandler:
    def __init__(self, dav_root: str) -> None:
        self._dav_root = dav_root

    async def __call__(self, request):
        from aiohttp import web

        return web.HTTPFound(self._dav_root)


MDNS_NAME = "Xandikos CalDAV/CardDAV service"


def avahi_register(port: int, path: str):
    import avahi
    import dbus

    bus = dbus.SystemBus()
    server = dbus.Interface(
        bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER),
        avahi.DBUS_INTERFACE_SERVER,
    )
    group = dbus.Interface(
        bus.get_object(avahi.DBUS_NAME, server.EntryGroupNew()),
        avahi.DBUS_INTERFACE_ENTRY_GROUP,
    )

    for service in ["_carddav._tcp", "_caldav._tcp"]:
        try:
            group.AddService(
                avahi.IF_UNSPEC,
                avahi.PROTO_INET,
                0,
                MDNS_NAME,
                service,
                "",
                "",
                port,
                avahi.string_array_to_txt_array([f"path={path}"]),
            )
        except dbus.DBusException as e:
            logging.error("Error registering %s: %s", service, e)

    group.Commit()


def run_simple_server(
    directory: str,
    current_user_principal: str,
    autocreate: bool = False,
    defaults: bool = False,
    strict: bool = True,
    route_prefix: str = "/",
    listen_address: str | None = "::",
    port: int | None = 8080,
    socket_path: str | None = None,
) -> None:
    """Simple function to run a Xandikos server.

    This function is meant to be used by external code. We'll try our best
    not to break API compatibility.

    Args:
      directory: Directory to store data in ("/tmp/blah")
      current_user_principal: Name of current user principal ("/user")
      autocreate: Whether to create missing principals and collections
      defaults: Whether to create default calendar and addressbook collections
      strict: Whether to be strict in *DAV implementation. Set to False for
         buggy clients
      route_prefix: Route prefix under which to server ("/")
      listen_address: IP address to listen on (None to disable)
      port: TCP Port to listen on (None to disable)
      socket_path: Unix domain socket path to listen on (None to disable)
    """
    backend = XandikosBackend(directory)
    backend._mark_as_principal(current_user_principal)

    if autocreate or defaults:
        if not os.path.isdir(directory):
            os.makedirs(directory)
        backend.create_principal(current_user_principal, create_defaults=defaults)

    if not os.path.isdir(directory):
        logging.warning(
            "%r does not exist. Run xandikos with --autocreate?",
            directory,
        )
    if not backend.get_resource(current_user_principal):
        logging.warning(
            "default user principal %s does not exist. Run xandikos with --autocreate?",
            current_user_principal,
        )

    main_app = XandikosApp(
        backend,
        current_user_principal=current_user_principal,
        strict=strict,
    )

    async def xandikos_handler(request):
        return await main_app.aiohttp_handler(request, route_prefix)

    if socket_path:
        logging.info("Listening on unix domain socket %s", socket_path)
    if listen_address and port:
        logging.info("Listening on %s:%s", listen_address, port)

    from aiohttp import web

    app = web.Application()
    for path in WELLKNOWN_DAV_PATHS:
        app.router.add_route("*", path, RedirectDavHandler(route_prefix).__call__)

    if route_prefix.strip("/"):
        xandikos_app = web.Application()
        xandikos_app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

        async def redirect_to_subprefix(request):
            return web.HTTPFound(route_prefix)

        app.router.add_route("*", "/", redirect_to_subprefix)
        app.add_subapp(route_prefix, xandikos_app)
    else:
        app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

    web.run_app(app, port=port, host=listen_address, path=socket_path)


def add_parser(parser):
    import argparse

    access_group = parser.add_argument_group(title="Access Options")
    access_group.add_argument(
        "--no-detect-systemd",
        action="store_false",
        dest="detect_systemd",
        help="Disable systemd detection and socket activation.",
        default=systemd_imported,
    )
    access_group.add_argument(
        "-l",
        "--listen-address",
        dest="listen_address",
        default="localhost",
        help=(
            "Bind to this address. Pass in path for unix domain socket. [%(default)s]"
        ),
    )
    access_group.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=8080,
        help="Port to listen on. [%(default)s]",
    )
    access_group.add_argument(
        "--metrics-port",
        dest="metrics_port",
        default=None,
        help="Port to listen on for metrics. [%(default)s]",
    )
    access_group.add_argument(
        "--route-prefix",
        default="/",
        help=(
            "Path to Xandikos. "
            "(useful when Xandikos is behind a reverse proxy) "
            "[%(default)s]"
        ),
    )
    parser.add_argument(
        "-d",
        "--directory",
        dest="directory",
        default=None,
        required=True,
        help="Directory to serve from.",
    )
    parser.add_argument(
        "--current-user-principal",
        default="/user/",
        help="Path to current user principal. [%(default)s]",
    )
    parser.add_argument(
        "--autocreate",
        action="store_true",
        dest="autocreate",
        help="Automatically create necessary directories.",
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        dest="defaults",
        help=("Create initial calendar and address book. Implies --autocreate."),
    )
    parser.add_argument(
        "--dump-dav-xml",
        action="store_true",
        dest="dump_dav_xml",
        help="Print DAV XML request/responses.",
    )
    parser.add_argument(
        "--avahi", action="store_true", help="Announce services with avahi."
    )
    parser.add_argument(
        "--no-strict",
        action="store_false",
        dest="strict",
        help=("Enable workarounds for buggy CalDAV/CardDAV client implementations."),
        default=True,
    )
    parser.add_argument("--debug", action="store_true", help="Print debug messages")
    # Hidden arguments. These may change without notice in between releases,
    # and are generally just meant for developers.
    parser.add_argument("--paranoid", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--index-threshold", type=int, help=argparse.SUPPRESS)


async def main(options, parser):
    if options.dump_dav_xml:
        # TODO(jelmer): Find a way to propagate this without abusing
        # os.environ.
        os.environ["XANDIKOS_DUMP_DAV_XML"] = "1"

    if not options.route_prefix.endswith("/"):
        options.route_prefix += "/"

    if options.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    logging.basicConfig(level=loglevel, format="%(message)s")

    backend = XandikosBackend(
        os.path.abspath(options.directory),
        paranoid=options.paranoid,
        index_threshold=options.index_threshold,
    )
    backend._mark_as_principal(options.current_user_principal)

    if options.autocreate or options.defaults:
        if not os.path.isdir(options.directory):
            os.makedirs(options.directory)
        backend.create_principal(
            options.current_user_principal, create_defaults=options.defaults
        )

    if not os.path.isdir(options.directory):
        logging.warning(
            "%r does not exist. Run xandikos with --autocreate?",
            options.directory,
        )
    if not backend.get_resource(options.current_user_principal):
        logging.warning(
            "default user principal %s does not exist. Run xandikos with --autocreate?",
            options.current_user_principal,
        )

    logging.info("Xandikos %s", ".".join(map(str, xandikos_version)))

    main_app = XandikosApp(
        backend,
        current_user_principal=options.current_user_principal,
        strict=options.strict,
    )

    async def xandikos_handler(request):
        return await main_app.aiohttp_handler(request, options.route_prefix)

    if options.detect_systemd and not systemd_imported:
        parser.error("systemd detection requested, but unable to find systemd_python")

    if options.detect_systemd and systemd.daemon.booted():
        listen_socks = get_systemd_listen_sockets()
        socket_path = None
        listen_address = None
        listen_port = None
        logging.info("Receiving file descriptors from systemd socket activation")
    elif "/" in options.listen_address:
        socket_path = options.listen_address
        listen_address = None
        listen_port = None  # otherwise aiohttp also listens on default host
        listen_socks = []
        logging.info("Listening on unix domain socket %s", socket_path)
    else:
        listen_address = options.listen_address
        listen_port = options.port
        socket_path = None
        listen_socks = []
        logging.info("Listening on %s:%s", listen_address, options.port)

    from aiohttp import web

    if options.metrics_port == options.port:
        parser.error("Metrics port cannot be the same as the main port")

    app = web.Application()
    if options.metrics_port is not None:
        metrics_app = web.Application()
        try:
            from aiohttp_openmetrics import metrics, metrics_middleware
        except ModuleNotFoundError:
            logging.warning(
                "aiohttp-openmetrics not found; /metrics will not be available."
            )
        else:
            app.middlewares.insert(0, metrics_middleware)
            metrics_app.router.add_get("/metrics", metrics, name="metrics")

        # For now, just always claim everything is okay.
        metrics_app.router.add_get("/health", lambda r: web.Response(text="ok"))
    else:
        metrics_app = None

    for path in WELLKNOWN_DAV_PATHS:
        app.router.add_route(
            "*", path, RedirectDavHandler(options.route_prefix).__call__
        )

    if options.route_prefix.strip("/"):
        xandikos_app = web.Application()
        xandikos_app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

        async def redirect_to_subprefix(request):
            return web.HTTPFound(options.route_prefix)

        app.router.add_route("*", "/", redirect_to_subprefix)
        app.add_subapp(options.route_prefix, xandikos_app)
    else:
        app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

    if options.avahi:
        try:
            import avahi  # noqa: F401
            import dbus  # noqa: F401
        except ImportError:
            logging.error(
                "Please install python-avahi and python-dbus for avahi support."
            )
        else:
            avahi_register(options.port, options.route_prefix)

    runner = web.AppRunner(app)
    await runner.setup()
    sites = []
    if metrics_app:
        metrics_runner = web.AppRunner(metrics_app)
        await metrics_runner.setup()
        # TODO(jelmer): Allow different metrics listen address?
        sites.append(web.TCPSite(metrics_runner, listen_address, options.metrics_port))
    # Use systemd sockets first and only if not present use the socket path or
    # address from --listen-address.
    if listen_socks:
        sites.extend([web.SockSite(runner, sock) for sock in listen_socks])
    elif socket_path:
        sites.append(web.UnixSite(runner, socket_path))
    else:
        sites.append(web.TCPSite(runner, listen_address, listen_port))

    import signal

    # Set up graceful shutdown handling
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logging.info("Received signal %s, shutting down gracefully...", signum)
        # Use call_soon_threadsafe to safely set the event from signal handler
        loop.call_soon_threadsafe(shutdown_event.set)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    for site in sites:
        await site.start()

    # Wait for shutdown signal
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down gracefully...")

    # Cleanup: stop all sites and runners
    logging.info("Stopping web servers...")
    for site in sites:
        await site.stop()

    await runner.cleanup()
    if metrics_app:
        await metrics_runner.cleanup()

    logging.info("Shutdown complete.")


if __name__ == "__main__":
    import sys

    import argparse

    parser = argparse.ArgumentParser(usage="%(prog)s [options]")
    add_parser(parser)
    args = parser.parse_args(sys.argv[1:])

    sys.exit(asyncio.run(main(args, parser)))
