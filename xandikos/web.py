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
import base64
import functools
import hashlib
import logging
from logging import getLogger
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
    imip,
    imip_listen,
    imip_transport as imip_transport_mod,
    milter,
    infit,
    itip,
    quota,
    scheduling,
    sync,
    timezones,
    webcal,
    webdav,
    webdav_push,
    xmpp,
)
from xandikos.fs import FilesystemBackend, open_store_from_path
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

from icalendar.cal import Calendar

from .icalendar import CalendarFilter, ICalendarFile
from .store.git import GitStore, TreeGitStore

logger = getLogger("xandikos")

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


WELLKNOWN_DAV_PATHS = {
    caldav.WELLKNOWN_CALDAV_PATH,
    carddav.WELLKNOWN_CARDDAV_PATH,
}


def default_state_dir() -> str:
    """Return the default directory for Xandikos server state.

    Uses ``$XDG_DATA_HOME/xandikos`` per the XDG Base Directory spec,
    falling back to ``~/.local/share/xandikos`` when the variable is
    unset or empty.
    """
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(data_home, "xandikos")


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
        parent: "StoreBasedCollection | None" = None,
    ) -> None:
        self.store = store
        self.name = name
        self.etag = etag
        self.content_type = content_type
        self._file = file
        # Parent collection, when known. Used so this resource can notify
        # the collection of its own changes (e.g. successful PUTs).
        self._parent = parent

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.store!r}, {self.name!r}, {self.etag!r}, {self.get_content_type()!r})"

    async def get_file(self) -> File:
        if self._file is None:
            self._file = await asyncio.to_thread(
                self.store.get_file, self.name, self.content_type, self.etag
            )
            assert self._file is not None
        return self._file

    async def get_body(self) -> Iterable[bytes]:
        file = await self.get_file()
        return file.content

    async def set_body(self, data, replace_etag=None, remote_user=None, requester=None):
        try:
            (name, etag) = await asyncio.to_thread(
                self.store.import_one,
                self.name,
                self.content_type,
                data,
                replace_etag=extract_strong_etag(replace_etag),
                remote_user=remote_user,
                requester=requester,
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
        if self._parent is not None:
            await self._parent.notify_content_changed()
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

    async def get_schedule_tag(self) -> str:
        if self.content_type != "text/calendar":
            raise KeyError
        file = await self.get_file()
        assert isinstance(file, ICalendarFile)
        cal = file.calendar
        assert isinstance(cal, Calendar)
        signature = itip.extract_scheduling_signature(cal)
        return create_strong_etag(signature.hex())


async def _run_change_listener(awaitable) -> None:
    try:
        await awaitable
    except Exception:  # noqa: BLE001
        logger.exception("change listener task failed")


class StoreBasedCollection:
    # Global change listeners. Each entry is a callable
    # ``(collection, kind, **details) -> Awaitable | None`` where
    # ``kind`` is ``"content"`` or ``"property"``. Async returns are
    # scheduled on the running event loop. Errors are logged and never
    # propagated to the originating request.
    _change_listeners: list = []

    def __init__(self, backend, relpath, store) -> None:
        self.backend = backend
        self.relpath = relpath
        self.store = store

    @classmethod
    def add_change_listener(cls, callback) -> None:
        """Register a global change listener for every store-based collection."""
        cls._change_listeners.append(callback)

    def _dispatch_change(self, kind: str, **details) -> None:
        for cb in list(self._change_listeners):
            try:
                result = cb(self, kind, **details)
            except Exception:  # noqa: BLE001
                logger.exception("change listener raised")
                continue
            if result is None:
                continue
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                if hasattr(result, "close"):
                    result.close()
                continue
            loop.create_task(_run_change_listener(result))

    async def notify_content_changed(self) -> None:
        self._dispatch_change("content")

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
        return ObjectResource(
            self.store, name, content_type, etag, file=file, parent=self
        )

    def _get_subcollection(self, name: str) -> webdav.Collection:
        return self.backend.get_resource(posixpath.join(self.relpath, name))

    def get_displayname(self) -> str:
        displayname = self.store.get_displayname()
        if displayname is None:
            return os.path.basename(self.store.repo.path)
        return displayname

    def set_displayname(self, displayname: str) -> None:
        self.store.set_displayname(displayname)
        self._dispatch_change("property", changed_properties=("{DAV:}displayname",))

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
        try:
            (content_type, etag) = self.store.get_file_meta(name)
        except KeyError:
            if name in self.store.subdirectories():
                return self._get_subcollection(name)
            raise KeyError(name)
        return self._get_resource(name, content_type, etag)

    def delete_member(self, name, etag=None, remote_user=None, requester=None):
        assert name != ""
        try:
            self.store.delete_one(
                name,
                etag=extract_strong_etag(etag),
                remote_user=remote_user,
                requester=requester,
            )
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
        self._dispatch_change("content")

    async def create_member(
        self,
        name: str | None,
        contents: Iterable[bytes],
        content_type: str,
        remote_user: str | None = None,
        requester: str | None = None,
    ) -> tuple[str, str]:
        # Check if member already exists and raise FileExistsError if it does
        if name is not None:
            try:
                existing_member = self.get_member(name)
                if existing_member is not None:
                    raise FileExistsError(f"Member '{name}' already exists")
            except KeyError:
                # Member doesn't exist, which is what we want for create_member
                pass

        try:
            (name, etag) = self.store.import_one(
                name,
                content_type,
                contents,
                remote_user=remote_user,
                requester=requester,
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
        await self.post_create_member_hook(name, contents, content_type)
        self._dispatch_change("content")
        return (name, create_strong_etag(etag))

    async def post_create_member_hook(
        self,
        name: str,
        contents: Iterable[bytes],
        content_type: str,
    ) -> None:
        """Run side-effects just after a member has been created.

        Default is a no-op. The schedule-inbox overrides this to
        auto-apply incoming iTIP messages to the principal's default
        calendar (RFC 6638 §3.1 implicit scheduling). Failures here
        do not roll the create back; the stored item is the canonical
        record and the auto-processing is best-effort.
        """
        return None

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
        self.backend._open_store.cache_clear()

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

    def get_schedule_default_calendar_url(self) -> str | None:
        """Return the default calendar URL for incoming iTIP messages.

        RFC 6638 §9.2: the inbox advertises a single calendar where
        clients should look (and where scheduling deliveries land) by
        default. The principal nominates the choice via PROPPATCH
        (persisted in the principal's ``.xandikos`` config);
        ``create_principal_defaults`` seeds it when called with
        ``--defaults``. Returns ``None`` if no default has been set:
        scheduling still works, clients just don't get a pre-chosen
        target.
        """
        owning = scheduling.find_owning_principal(self.backend, self.relpath)
        if owning is None:
            return None
        _, principal = owning
        try:
            return principal.get_schedule_default_calendar_url()
        except KeyError:
            return None

    def set_schedule_default_calendar_url(self, url: str | None) -> None:
        """Persist the default calendar choice on the owning principal.

        Stored in the principal's ``.xandikos`` config; ``None``
        unsets the override and restores the auto-pick.
        """
        owning = scheduling.find_owning_principal(self.backend, self.relpath)
        if owning is None:
            raise webdav.PreconditionFailure(
                "{%s}valid-schedule-default-calendar-URL" % caldav.NAMESPACE,
                "Cannot set schedule-default-calendar-URL: inbox has no "
                "owning principal.",
            )
        _, principal = owning
        principal.set_schedule_default_calendar_url(url)

    async def post_create_member_hook(
        self,
        name: str,
        contents: Iterable[bytes],
        content_type: str,
    ) -> None:
        """Auto-apply the just-stored iTIP message to the default calendar.

        RFC 6638 §3.1: when an iTIP message lands in a principal's
        schedule-inbox, the server should mirror its semantics into
        the principal's own calendar so the user's CalDAV client sees
        the state without having to read the inbox itself.

        - REQUEST → upsert into the default calendar, preserving any
          existing PARTSTAT on attendees we already know about.
        - CANCEL → mark the matching local copy STATUS:CANCELLED.
        - REPLY → update the sender's ATTENDEE PARTSTAT on the
          organiser's stored copy.

        The inbox copy itself is the canonical record of what
        arrived; we don't roll it back if auto-processing fails. If
        no default calendar is configured we silently skip — clients
        can still find the message in the inbox.
        """
        if content_type != "text/calendar":
            return
        try:
            parsed = Calendar.from_ical(b"".join(contents).decode("utf-8"))
        except ValueError as exc:
            logger.info(
                "Inbox auto-apply skipping %s: invalid iCalendar (%s)", name, exc
            )
            return
        if not isinstance(parsed, Calendar):
            logger.info(
                "Inbox auto-apply skipping %s: payload is not a VCALENDAR", name
            )
            return
        method_value = parsed.get("METHOD")
        method = str(method_value).upper() if method_value is not None else ""
        if method not in {"REQUEST", "CANCEL", "REPLY"}:
            logger.info(
                "Inbox auto-apply skipping %s: METHOD %r is not actionable",
                name,
                method,
            )
            return

        calendar = self._default_calendar()
        if calendar is None:
            logger.info(
                "Inbox auto-apply skipping %s iTIP %s: no schedule-default-calendar-URL set",
                name,
                method,
            )
            return
        uid = itip.itip_uid(parsed)
        if uid is None:
            logger.info(
                "Inbox auto-apply skipping %s iTIP %s: no UID in payload", name, method
            )
            return
        existing = await _find_calendar_member_by_uid(calendar, uid)

        if method == "REQUEST":
            await self._apply_request(calendar, parsed, existing, uid)
        elif method == "CANCEL":
            await self._apply_cancel(parsed, uid, existing)
        elif method == "REPLY":
            await self._apply_reply(parsed, uid, existing)

    def _default_calendar(self) -> "CalendarCollection | None":
        url = self.get_schedule_default_calendar_url()
        if url is None:
            return None
        cal = self.backend.get_resource(url)
        if not isinstance(cal, CalendarCollection):
            return None
        return cal

    async def _apply_request(
        self,
        calendar: "CalendarCollection",
        itip_message: Calendar,
        existing: "tuple[str, ObjectResource, Calendar] | None",
        uid: str,
    ) -> None:
        new_cal = itip.strip_method(itip_message)
        if existing is None:
            await calendar.create_member(None, [new_cal.to_ical()], "text/calendar")
            logger.info(
                "Inbox auto-apply: created %s in %s for REQUEST",
                uid,
                calendar.relpath,
            )
            return
        member_name, member, existing_cal = existing
        merged = itip.preserve_partstats(existing_cal, new_cal)
        await _replace_member_body(member, merged)
        logger.info(
            "Inbox auto-apply: updated %s (%s) in %s for REQUEST",
            uid,
            member_name,
            calendar.relpath,
        )

    async def _apply_cancel(
        self,
        itip_message: Calendar,
        uid: str,
        existing: "tuple[str, ObjectResource, Calendar] | None",
    ) -> None:
        if existing is None:
            logger.info(
                "Inbox auto-apply: CANCEL for %s found no local copy to cancel", uid
            )
            return
        member_name, member, existing_cal = existing
        for comp in existing_cal.subcomponents:
            if (
                comp.name in itip.SCHEDULING_COMPONENTS
                and str(comp.get("UID", "")) == uid
            ):
                comp["STATUS"] = "CANCELLED"
        await _replace_member_body(member, existing_cal)
        logger.info("Inbox auto-apply: cancelled %s (%s)", uid, member_name)

    async def _apply_reply(
        self,
        itip_message: Calendar,
        uid: str,
        existing: "tuple[str, ObjectResource, Calendar] | None",
    ) -> None:
        if existing is None:
            logger.info(
                "Inbox auto-apply: REPLY for %s found no local copy to update", uid
            )
            return
        member_name, member, existing_cal = existing

        # Pick out the replying attendee's address + new PARTSTAT.
        updates: dict[str, str] = {}
        for comp in itip_message.subcomponents:
            if comp.name not in itip.SCHEDULING_COMPONENTS:
                continue
            if str(comp.get("UID", "")) != uid:
                continue
            attendees = comp.get("ATTENDEE", [])
            if not isinstance(attendees, list):
                attendees = [attendees]
            for a in attendees:
                partstat = a.params.get("PARTSTAT")
                if partstat is not None:
                    updates[str(a)] = str(partstat)
        if not updates:
            return

        changed = False
        for comp in existing_cal.subcomponents:
            if comp.name not in itip.SCHEDULING_COMPONENTS:
                continue
            if str(comp.get("UID", "")) != uid:
                continue
            attendees = comp.get("ATTENDEE", [])
            if not isinstance(attendees, list):
                attendees = [attendees]
            for a in attendees:
                new_partstat = updates.get(str(a))
                if (
                    new_partstat is not None
                    and a.params.get("PARTSTAT") != new_partstat
                ):
                    a.params["PARTSTAT"] = new_partstat
                    changed = True
        if changed:
            await _replace_member_body(member, existing_cal)
            logger.info(
                "Inbox auto-apply: applied REPLY to %s (%s); updated PARTSTATs: %s",
                uid,
                member_name,
                ", ".join(f"{addr}={ps}" for addr, ps in updates.items()),
            )
        else:
            logger.info(
                "Inbox auto-apply: REPLY for %s (%s) had no new PARTSTATs to apply",
                uid,
                member_name,
            )


async def _find_calendar_member_by_uid(
    calendar: "CalendarCollection", uid: str
) -> "tuple[str, ObjectResource, Calendar] | None":
    """Find a member of *calendar* whose VCALENDAR has an event with *uid*.

    Returns ``(name, ObjectResource, parsed_calendar)`` or None. The
    ObjectResource is returned alongside the parsed calendar so
    callers can update it in place without re-resolving.
    """
    for name, member in calendar.members():
        if not isinstance(member, ObjectResource):
            continue
        if member.get_content_type() != "text/calendar":
            continue
        file = await member.get_file()
        if not isinstance(file, ICalendarFile):
            continue
        cal = file.calendar
        if not isinstance(cal, Calendar):
            continue
        for comp in cal.subcomponents:
            if (
                comp.name in itip.SCHEDULING_COMPONENTS
                and str(comp.get("UID", "")) == uid
            ):
                return name, member, cal
    return None


async def _replace_member_body(member: "ObjectResource", new_cal: Calendar) -> None:
    """Replace *member*'s body with *new_cal*'s serialized bytes."""
    body = new_cal.to_ical()
    etag = await member.get_etag()
    await member.set_body([body], replace_etag=etag)


class ScheduleOutbox(StoreBasedCollection, scheduling.ScheduleOutbox):
    """A schedling outbox collection."""

    async def get_attendee_busy_periods(self, attendee_address, start, end):
        """Look up busy periods for *attendee_address* within [start, end).

        Returns ``None`` if the address does not belong to this outbox's
        principal — that is, the server has no authority to answer for
        this attendee. Otherwise walks the principal's calendar-home and
        gathers busy/availability periods via :func:`caldav.iter_freebusy`.
        """
        owning = scheduling.find_owning_principal(self.backend, self.relpath)
        if owning is None:
            return None
        principal_path, principal = owning
        if attendee_address not in principal.get_calendar_user_address_set():
            return None

        from zoneinfo import ZoneInfo

        utc = ZoneInfo("UTC")

        def tzify(dt):
            from .icalendar import as_tz_aware_ts

            return as_tz_aware_ts(dt, utc).astimezone(utc)

        own_addresses = set(principal.get_calendar_user_address_set())
        periods = []
        for home in principal.get_calendar_home_set():
            home_path = posixpath.join(principal_path, home)
            home_resource = self.backend.get_resource(home_path)
            if home_resource is None:
                continue
            for cal_name, cal_resource in home_resource.members():
                if caldav.CALENDAR_RESOURCE_TYPE not in cal_resource.resource_types:
                    continue
                # Calendars marked TRANSPARENT contribute no busy time —
                # they're advisory (e.g. holidays, work calendars on a
                # personal account).
                if (
                    cal_resource.get_schedule_calendar_transparency()
                    == caldav.TRANSPARENCY_TRANSPARENT
                ):
                    continue
                cal_path = posixpath.join(home_path, cal_name)
                async for period in caldav.iter_freebusy(
                    webdav.traverse_resource(cal_resource, cal_path, "infinity"),
                    start,
                    end,
                    tzify,
                    own_addresses=own_addresses,
                ):
                    periods.append(period)
        return periods


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
    async def create_member(
        self,
        name: str | None,
        contents: Iterable[bytes],
        content_type: str,
        remote_user: str | None = None,
        requester: str | None = None,
    ) -> tuple[str, str]:
        """Create a new member with validation for calendar collections."""
        if content_type != "text/calendar":
            raise webdav.PreconditionFailure(
                "{%s}valid-calendar-data" % caldav.NAMESPACE,
                f"Calendar collections only support calendar files. Got: {content_type}",
            )
        return await super().create_member(
            name, contents, content_type, remote_user, requester
        )

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

    async def render(
        self, self_url, accepted_content_types, accepted_content_languages
    ):
        query = urllib.parse.urlparse(self_url).query
        export_requested = "export" in urllib.parse.parse_qs(
            query, keep_blank_values=True
        )
        if export_requested:
            serve_ics = True
        else:
            # Only serve text/calendar when the client explicitly asked
            # for it (e.g. Accept: text/calendar). Fall back to HTML for
            # */* so browsers keep getting the human-readable view.
            try:
                content_types = webdav.pick_content_types(
                    accepted_content_types, ["text/html"]
                )
            except webdav.NotAcceptableError:
                content_types = webdav.pick_content_types(
                    accepted_content_types, ["text/calendar"]
                )
            serve_ics = content_types == ["text/calendar"]
        if serve_ics:
            try:
                displayname = self.get_displayname()
            except KeyError:
                displayname = None
            try:
                description = self.get_calendar_description()
            except (KeyError, NotImplementedError):
                description = None
            try:
                timezone = self.get_calendar_timezone()
            except (KeyError, NotImplementedError):
                timezone = None
            body = webcal.merge_store_calendar(
                self.store,
                displayname=displayname,
                description=description,
                timezone=timezone,
            ).to_ical()
            return (
                [body],
                len(body),
                await self.get_etag(),
                "text/calendar; charset=utf-8",
                None,
            )
        return await super().render(
            self_url, accepted_content_types, accepted_content_languages
        )

    def get_xmpp_heartbeat(self):
        # TODO
        raise KeyError

    def get_xmpp_server(self):
        # TODO
        raise KeyError

    def get_xmpp_uri(self):
        # TODO
        raise KeyError

    async def pre_delete_hook(self, member_name: str) -> None:
        """Generate an iTIP CANCEL when the organiser deletes a meeting.

        Per RFC 6638 §3.2.2: when a Calendar User deletes a scheduling
        object resource where they are the ORGANIZER, the server should
        notify the attendees. We deliver an iTIP CANCEL to each local
        attendee's schedule-inbox; remote attendees would need iMIP and
        are skipped for now.
        """
        try:
            member = self.get_member(member_name)
        except KeyError:
            return
        cal = await _calendar_from_member(member)
        if cal is None:
            return

        principal = self._owning_principal()
        if principal is None:
            return
        organiser_addresses = set(principal.get_calendar_user_address_set())

        is_organiser, attendees = _organiser_attendees(cal, organiser_addresses)
        if not is_organiser or not attendees:
            return

        cancel = itip.build_itip_cancel(cal)
        organiser = _organiser_address(cal)
        for address in attendees:
            await _deliver_status(self.backend, address, cancel, originator=organiser)

    async def pre_put_hook(
        self,
        member_name: str,
        new_contents: Iterable[bytes],
        content_type: str,
    ) -> Iterable[bytes] | None:
        """Generate iTIP traffic when the user PUTs a scheduling object.

        Two paths, exclusive on a per-event basis:

        Organiser (RFC 6638 §3.2.1) — the user is ORGANIZER of the new
        event. Each current attendee gets an iTIP REQUEST; each
        attendee dropped relative to the prior version gets an iTIP
        CANCEL. The returned bytes carry SCHEDULE-STATUS annotations
        on each ATTENDEE describing the delivery outcome (1.2 for
        local delivery, 3.7 for unknown calendar user).

        Attendee (RFC 6638 §3.2.2) — the user is in ATTENDEE on the
        new event but isn't ORGANIZER. If their PARTSTAT changed (or
        they were just added) since the prior version, send an iTIP
        REPLY to the organiser narrowed to the user's own ATTENDEE
        line. A first-time import without prior version emits no
        REPLY — we have no evidence the user's PARTSTAT actually moved.

        If the new content's scheduling-signature matches the old, no
        iTIP traffic is generated — schedule-tag changes only on
        iTIP-relevant edits, and so does this hook.
        """
        if content_type != "text/calendar":
            return None
        try:
            parsed = Calendar.from_ical(b"".join(new_contents).decode("utf-8"))
        except ValueError:
            # Let the regular PUT path raise the proper precondition.
            return None
        if not isinstance(parsed, Calendar):
            return None
        new_cal = parsed

        principal = self._owning_principal()
        if principal is None:
            return None
        own_addresses = set(principal.get_calendar_user_address_set())

        old_cal: Calendar | None = None
        try:
            existing = self.get_member(member_name)
        except KeyError:
            existing = None
        if existing is not None:
            old_cal = await _calendar_from_member(existing)

        # SCHEDULE-FORCE-SEND (RFC 6638 §3.2.4) is a client-only
        # parameter; consume it from new_cal so it doesn't end up
        # stored. The captured addresses bypass the normal "nothing
        # changed, skip" short-circuit and the PARTSTAT-changed gate.
        force_request, force_reply, rewrite_needed = _consume_force_send(new_cal)

        old_delegates = (
            _delegates_of(old_cal, own_addresses) if old_cal is not None else set()
        )
        new_delegates = _delegates_of(new_cal, own_addresses) - old_delegates

        if old_cal is not None:
            new_sig = itip.extract_scheduling_signature(new_cal)
            old_sig = itip.extract_scheduling_signature(old_cal)
            if new_sig == old_sig and not (force_request or force_reply):
                return [new_cal.to_ical()] if rewrite_needed else None

            # RFC 6638 §3.1: an attendee may only modify their own
            # ATTENDEE entry on a stored scheduling object — the rest
            # of the event (DTSTART/DTEND, ATTENDEE list, ORGANIZER,
            # SUMMARY, …) is owned by the organiser. If the user was
            # an attendee on the prior version (and not also the
            # organiser), check that they aren't reaching past their
            # own ATTENDEE entry. Adding an ATTENDEE that's a
            # delegate of the user (DELEGATED-FROM matching one of
            # own_addresses) is the documented exception
            # (RFC 6638 §3.2.6).
            old_was_organiser, _ = _organiser_attendees(old_cal, own_addresses)
            old_was_attendee = _own_attendee_address(old_cal, own_addresses) is not None
            if old_was_attendee and not old_was_organiser:
                self._reject_unauthorised_attendee_change(
                    new_cal, old_cal, own_addresses, new_delegates
                )

        is_organiser, new_attendees = _organiser_attendees(new_cal, own_addresses)
        if is_organiser:
            outcomes = await self._dispatch_organiser_put(
                new_cal, old_cal, new_attendees, own_addresses
            )
            if outcomes:
                _annotate_schedule_status(new_cal, outcomes)
                return [new_cal.to_ical()]
            if rewrite_needed:
                return [new_cal.to_ical()]
            return None

        outcomes = await self._dispatch_attendee_put(
            new_cal, old_cal, own_addresses, force_reply, new_delegates
        )
        if outcomes:
            _annotate_schedule_status(new_cal, outcomes)
            return [new_cal.to_ical()]
        if rewrite_needed:
            return [new_cal.to_ical()]
        return None

    def _reject_unauthorised_attendee_change(
        self,
        new_cal: Calendar,
        old_cal: Calendar,
        own_addresses: set[str],
        new_delegates: set[str],
    ) -> None:
        """Raise if *new_cal* changes anything beyond the user's own ATTENDEE.

        Compares scheduling signatures of *old_cal* and *new_cal* with
        the user's own ATTENDEE parameters masked, and any newly-added
        delegates skipped entirely (RFC 6638 §3.2.6 lets an attendee
        add a delegate ATTENDEE, distinguishable by its DELEGATED-FROM
        pointing back at the user). If anything else differs, the user
        is touching organiser-owned data.
        """
        mask = frozenset(own_addresses)
        skip = frozenset(new_delegates)
        new_masked = itip.extract_scheduling_signature(
            new_cal, mask_own_attendee_params=mask, skip_attendees=skip
        )
        old_masked = itip.extract_scheduling_signature(
            old_cal, mask_own_attendee_params=mask, skip_attendees=skip
        )
        if new_masked != old_masked:
            raise webdav.PreconditionFailure(
                "{%s}attendee-allowed" % caldav.NAMESPACE,
                "Attendees may only modify their own ATTENDEE entry "
                "(or add delegates via DELEGATED-FROM); other event "
                "properties are organiser-owned (RFC 6638 §3.1).",
            )

    async def _dispatch_organiser_put(
        self,
        new_cal: Calendar,
        old_cal: Calendar | None,
        new_attendees: set[str],
        own_addresses: set[str],
    ) -> dict[str, str]:
        """Send REQUEST/CANCEL and return ``{address: SCHEDULE-STATUS code}``."""
        outcomes: dict[str, str] = {}
        organiser = _organiser_address(new_cal)
        if new_attendees:
            request = itip.build_itip_request(new_cal)
            for address in new_attendees:
                outcomes[address] = await _deliver_status(
                    self.backend, address, request, originator=organiser
                )

        if old_cal is None:
            return outcomes
        _, old_attendees = _organiser_attendees(old_cal, own_addresses)
        dropped = old_attendees - new_attendees
        if dropped:
            cancel = itip.build_itip_cancel(old_cal)
            for address in dropped:
                # Dropped attendees aren't in new_cal, so their CANCEL
                # delivery outcomes don't end up annotated anywhere; the
                # CANCEL itself is the record. Still goes through the
                # iMIP path for non-local recipients.
                await _deliver_status(
                    self.backend, address, cancel, originator=organiser
                )
        return outcomes

    async def _dispatch_attendee_put(
        self,
        new_cal: Calendar,
        old_cal: Calendar | None,
        own_addresses: set[str],
        force_reply: set[str],
        new_delegates: set[str],
    ) -> dict[str, str]:
        """Send REPLY to organiser and REQUEST to any newly-added delegates.

        Returns ``{address: SCHEDULE-STATUS code}`` for the delegate
        deliveries; the REPLY itself isn't annotated (the user's own
        ATTENDEE doesn't carry SCHEDULE-STATUS).
        """
        outcomes: dict[str, str] = {}
        own_address = _own_attendee_address(new_cal, own_addresses)

        # RFC 6638 §3.2.6: when the user delegates to someone else,
        # the new delegate needs a REQUEST so they see the meeting.
        if new_delegates:
            request = itip.build_itip_request(new_cal)
            for address in new_delegates:
                outcomes[address] = await _deliver_status(
                    self.backend, address, request, originator=own_address
                )

        if own_address is None:
            return outcomes
        organiser = _organiser_address(new_cal)
        if organiser is None or organiser in own_addresses:
            # Self-organised events have nothing to reply to.
            return outcomes
        # REPLY semantics need a prior version to compare PARTSTAT
        # against. On a first PUT (no prior) the only thing this path
        # might have done is dispatch delegate REQUESTs above; nothing
        # to REPLY to.
        if old_cal is None:
            return outcomes
        # SCHEDULE-FORCE-SEND=REPLY on the user's own ATTENDEE
        # (RFC 6638 §3.2.4) bypasses the PARTSTAT-changed gate.
        forced = own_address in force_reply
        if not forced and not _partstat_changed(new_cal, old_cal, own_address):
            return outcomes
        reply = itip.build_itip_reply(new_cal, own_address)
        await _deliver_status(self.backend, organiser, reply, originator=own_address)
        return outcomes

    def _owning_principal(self) -> webdav.Principal | None:
        owning = scheduling.find_owning_principal(self.backend, self.relpath)
        if owning is None:
            return None
        return owning[1]


async def _calendar_from_member(member: webdav.Resource) -> Calendar | None:
    """Return the parsed Calendar of *member*, or None if not iCalendar."""
    if not isinstance(member, ObjectResource):
        return None
    if member.get_content_type() != "text/calendar":
        return None
    file = await member.get_file()
    if not isinstance(file, ICalendarFile):
        return None
    cal = file.calendar
    if not isinstance(cal, Calendar):
        return None
    return cal


async def _deliver_status(
    backend: webdav.Backend,
    address: str,
    message: Calendar,
    *,
    originator: str | None = None,
) -> str:
    """Deliver *message* to *address* and return a SCHEDULE-STATUS code.

    Tries local-inbox delivery first (success → ``2.0;Success``). For
    addresses that don't belong to a local principal, falls through to
    iMIP if the backend is configured with a transport: success →
    ``1.1;Sent``, transport failure → ``5.1;Service unavailable``,
    and ``--imip-send=off`` → ``3.7;Invalid calendar user`` (the
    pre-iMIP behaviour). *originator* is the originating
    organiser/attendee address used for the iMIP ``Reply-To:`` header.
    Storage failures from local delivery propagate.
    """
    delivered = await scheduling.deliver_to_inbox(
        backend, address, message, name_hint=None
    )
    if delivered:
        return itip.REQUEST_STATUS_SUCCESS
    return await _send_via_imip(backend, originator, address, message)


async def _send_via_imip(
    backend: webdav.Backend,
    originator: str | None,
    recipient: str,
    message: Calendar,
) -> str:
    """Hand *message* to the configured outbound iMIP transport.

    Returns the SCHEDULE-STATUS code reflecting the outcome. Backends
    that don't carry iMIP configuration (i.e. anything other than
    :class:`SingleUserFilesystemBackend`) behave as if iMIP is off.
    """
    if not isinstance(backend, SingleUserFilesystemBackend):
        return itip.REQUEST_STATUS_INVALID_CALENDAR_USER
    transport = backend.imip_transport
    sender = backend.imip_from
    if isinstance(transport, imip_transport_mod.NullTransport):
        return itip.REQUEST_STATUS_INVALID_CALENDAR_USER
    if sender is None:
        logger.warning(
            "Outbound iMIP enabled but no --smtp-from configured; "
            "skipping delivery to %s",
            recipient,
        )
        return itip.REQUEST_STATUS_INVALID_CALENDAR_USER
    email = imip.build_message(
        message,
        sender=sender,
        recipient=_strip_mailto(recipient),
        reply_to=_strip_mailto(originator) if originator else None,
        auto_submitted="auto-generated",
    )
    try:
        transport.send(email)
    except imip_transport_mod.IMIPTransportError as exc:
        logger.warning("iMIP delivery to %s failed: %s", recipient, exc)
        return itip.REQUEST_STATUS_TRANSPORT_UNAVAILABLE
    return itip.REQUEST_STATUS_SENT


def _strip_mailto(address: str) -> str:
    """Return *address* with any ``mailto:`` prefix removed."""
    if address.lower().startswith("mailto:"):
        return address[len("mailto:") :]
    return address


def _annotate_schedule_status(cal: Calendar, outcomes: dict[str, str]) -> None:
    """Stamp SCHEDULE-STATUS on each ATTENDEE per RFC 6638 §3.2.

    *outcomes* maps an attendee address (as it appears in ATTENDEE) to
    a request-status code. Attendees absent from *outcomes* are left
    alone — typically the organiser themselves, who we don't deliver
    to.
    """
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        attendees = comp.get("ATTENDEE", [])
        if not isinstance(attendees, list):
            attendees = [attendees]
        for a in attendees:
            status = outcomes.get(str(a))
            if status is not None:
                a.params["SCHEDULE-STATUS"] = status


def _consume_force_send(cal: Calendar) -> tuple[set[str], set[str], bool]:
    """Find and strip SCHEDULE-FORCE-SEND parameters on ATTENDEE entries.

    RFC 6638 §3.2.4: a client may attach ``SCHEDULE-FORCE-SEND=REQUEST``
    or ``SCHEDULE-FORCE-SEND=REPLY`` to an ATTENDEE to instruct the
    server to dispatch an iTIP message to that attendee even when no
    iTIP-significant change has happened. The parameter is a request
    to the server and is removed from the stored representation.

    Returns ``(force_request, force_reply, stripped)``. The first two
    are sets of attendee addresses by FORCE-SEND value. ``stripped``
    is True if any SCHEDULE-FORCE-SEND parameter was removed
    (including ones with unrecognised values, which are dropped per
    the spec but don't trigger delivery). ``cal`` is mutated in place.
    """
    force_request: set[str] = set()
    force_reply: set[str] = set()
    stripped = False
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        attendees = comp.get("ATTENDEE", [])
        if not isinstance(attendees, list):
            attendees = [attendees]
        for a in attendees:
            value = a.params.get("SCHEDULE-FORCE-SEND")
            if value is None:
                continue
            mode = str(value).upper()
            del a.params["SCHEDULE-FORCE-SEND"]
            stripped = True
            if mode == "REQUEST":
                force_request.add(str(a))
            elif mode == "REPLY":
                force_reply.add(str(a))
            # Other values are silently ignored per RFC 6638 §3.2.4.
    return force_request, force_reply, stripped


def _organiser_attendees(
    cal: Calendar, organiser_addresses: set[str]
) -> tuple[bool, set[str]]:
    """Return (is_organiser, attendee_addresses) for *cal*.

    ``is_organiser`` is True iff at least one scheduling component lists
    one of *organiser_addresses* as ORGANIZER. ``attendee_addresses``
    collects every ATTENDEE that isn't the organiser themselves
    (delivering iTIP back to the organiser's own inbox would just create
    noise).
    """
    attendees: set[str] = set()
    is_organiser = False
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        organiser = comp.get("ORGANIZER")
        if organiser is None or str(organiser) not in organiser_addresses:
            continue
        is_organiser = True
        comp_attendees = comp.get("ATTENDEE", [])
        if not isinstance(comp_attendees, list):
            comp_attendees = [comp_attendees]
        for a in comp_attendees:
            addr = str(a)
            if addr not in organiser_addresses:
                attendees.add(addr)
    return is_organiser, attendees


def _delegates_of(cal: Calendar, own_addresses: set[str]) -> set[str]:
    """Return ATTENDEE addresses delegated FROM one of *own_addresses*.

    RFC 5545 §3.8.4.4: an ATTENDEE may carry DELEGATED-FROM listing
    the address(es) that delegated to them. We pick the entries
    whose DELEGATED-FROM matches the user — those are the user's
    delegates and the user is allowed to add them on a PUT
    (RFC 6638 §3.2.6).
    """
    out: set[str] = set()
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        comp_attendees = comp.get("ATTENDEE", [])
        if not isinstance(comp_attendees, list):
            comp_attendees = [comp_attendees]
        for a in comp_attendees:
            delegated_from = a.params.get("DELEGATED-FROM")
            if delegated_from is None:
                continue
            sources = (
                delegated_from if isinstance(delegated_from, list) else [delegated_from]
            )
            if any(str(src) in own_addresses for src in sources):
                out.add(str(a))
    return out


def _own_attendee_address(cal: Calendar, own_addresses: set[str]) -> str | None:
    """Return the user's own attendee address as it appears in *cal*, or None.

    Picks the first match from any scheduling component. The address is
    returned in its canonical form (with case preserved).
    """
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        comp_attendees = comp.get("ATTENDEE", [])
        if not isinstance(comp_attendees, list):
            comp_attendees = [comp_attendees]
        for a in comp_attendees:
            addr = str(a)
            if addr in own_addresses:
                return addr
    return None


def _organiser_address(cal: Calendar) -> str | None:
    """Return the ORGANIZER address from *cal*, or None.

    A scheduling object has at most one organiser; we pick the first
    one we find across components.
    """
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        organiser = comp.get("ORGANIZER")
        if organiser is not None:
            return str(organiser)
    return None


def _partstat_changed(new_cal: Calendar, old_cal: Calendar, address: str) -> bool:
    """Return True iff the user's PARTSTAT differs between *old_cal* and *new_cal*.

    Treats "wasn't there before" as a change too — a freshly added
    attendee should reply at least once. Components are matched by the
    component name + UID + RECURRENCE-ID triple so per-instance
    overrides are compared independently.
    """
    return _user_partstats(new_cal, address) != _user_partstats(old_cal, address)


def _user_partstats(cal: Calendar, address: str) -> dict[tuple[str, str, str], str]:
    """Map (component-name, UID, RECURRENCE-ID) → PARTSTAT for *address*."""
    out: dict[tuple[str, str, str], str] = {}
    for comp in cal.subcomponents:
        if comp.name not in itip.SCHEDULING_COMPONENTS:
            continue
        comp_attendees = comp.get("ATTENDEE", [])
        if not isinstance(comp_attendees, list):
            comp_attendees = [comp_attendees]
        for a in comp_attendees:
            if str(a) != address:
                continue
            uid = str(comp.get("UID", ""))
            rid = str(comp.get("RECURRENCE-ID", ""))
            partstat = str(a.params.get("PARTSTAT", "NEEDS-ACTION"))
            out[(comp.name, uid, rid)] = partstat
            break
    return out


class AddressbookCollection(StoreBasedCollection, carddav.Addressbook):
    async def create_member(
        self,
        name: str | None,
        contents: Iterable[bytes],
        content_type: str,
        remote_user: str | None = None,
        requester: str | None = None,
    ) -> tuple[str, str]:
        """Create a new member with validation for addressbook collections.

        RFC 6352 Section 5.1: Address object resources contained in address book
        collections MUST contain a single vCard component only.
        """
        # RFC 6350: text/vcard is the standard, but we also support deprecated formats
        # that might exist in repositories: text/x-vcard and text/directory
        if content_type not in ("text/vcard", "text/x-vcard", "text/directory"):
            raise webdav.PreconditionFailure(
                "{%s}supported-address-data" % carddav.NAMESPACE,
                f"Addressbook collections only support vCard files. Got: {content_type}",
            )
        return await super().create_member(
            name, contents, content_type, remote_user, requester
        )

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
            logger.info("Creating %s", path)
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

    def delete_member(self, name, etag=None, remote_user=None, requester=None):
        # This doesn't have any non-collection members.
        self.get_member(name).destroy()

    def destroy(self):
        p = self.backend._map_to_file_path(self.relpath)
        # RFC2518, section 8.6.2 says this should recursively delete.
        shutil.rmtree(p)
        self.backend._open_store.cache_clear()

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

    def __init__(self, backend, show_principals: bool = True) -> None:
        self.backend = backend
        self.show_principals = show_principals

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

        principals = self.backend.find_principals() if self.show_principals else []

        return render_jinja_page(
            "root.html",
            accepted_content_languages,
            principals=principals,
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

    def delete_member(self, name, etag=None, remote_user=None, requester=None):
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
        """Return calendar-home-set paths for this principal.

        Reads from the principal's ``.xandikos`` config, falling back
        to :data:`CALENDAR_HOME_SET` when no override is configured.
        Set via the ``[principal]`` ``calendar-home-set`` key.
        """
        try:
            return self._metadata().get_calendar_home_set()
        except KeyError:
            return CALENDAR_HOME_SET

    def set_calendar_home_set(self, paths: list[str]) -> None:
        """Persist the principal's calendar-home-set override.

        Pass an empty list to unset the override and restore the
        :data:`CALENDAR_HOME_SET` default.
        """
        self._metadata().set_calendar_home_set(paths)

    def get_addressbook_home_set(self):
        """Return addressbook-home-set paths for this principal.

        Reads from the principal's ``.xandikos`` config, falling back
        to :data:`ADDRESSBOOK_HOME_SET` when no override is configured.
        Set via the ``[principal]`` ``addressbook-home-set`` key.
        """
        try:
            return self._metadata().get_addressbook_home_set()
        except KeyError:
            return ADDRESSBOOK_HOME_SET

    def set_addressbook_home_set(self, paths: list[str]) -> None:
        """Persist the principal's addressbook-home-set override.

        Pass an empty list to unset the override and restore the
        :data:`ADDRESSBOOK_HOME_SET` default.
        """
        self._metadata().set_addressbook_home_set(paths)

    def get_calendar_user_address_set(self):
        """Return this principal's calendar user addresses.

        Delegates the storage to :class:`FileBasedCollectionMetadata`
        backed by the principal's ``.xandikos`` config file. When no
        addresses are configured, falls back to a single ``mailto:``
        derived from the backend's default email. This default is only
        set in single-user mode, so multi-user deployments never share
        one address across principals. The config is written through
        PROPPATCH on the ``calendar-user-address-set`` property.
        """
        try:
            return self._metadata().get_calendar_user_address_set()
        except KeyError:
            pass
        ret = []
        if self.backend.default_email:
            (fullname, email) = parseaddr(self.backend.default_email)
            if email:
                ret.append("mailto:" + email)
        return ret

    def set_calendar_user_address_set(self, addresses: list[str]) -> None:
        """Persist the principal's calendar-user-address-set.

        Delegates to :class:`FileBasedCollectionMetadata` backed by
        the principal's ``.xandikos`` config file. Passing an empty
        list unsets the key, restoring the env-var fallback.
        """
        self._metadata().set_calendar_user_address_set(addresses)

    def _metadata(self):
        """Return a CollectionMetadata view of the principal's .xandikos.

        Principals don't have a Store the way collections do, so we
        construct a :class:`FileBasedCollectionMetadata` directly
        against the dotfile.
        """
        import configparser

        from xandikos.store.config import FileBasedCollectionMetadata

        path = self.backend._map_to_file_path(posixpath.join(self.relpath, ".xandikos"))
        cp = configparser.ConfigParser()
        if os.path.exists(path):
            cp.read(path)

        def save(cp, _message):
            with open(path, "w") as f:
                cp.write(f)

        return FileBasedCollectionMetadata(cp, save=save)

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
        """Return the calendar-user-type for this principal.

        Reads from the principal's ``.xandikos`` config (a
        :class:`FileBasedCollectionMetadata` instance), falling back
        to ``INDIVIDUAL`` (RFC 6638 §2.4.2's default) when nothing is
        configured. Set via PROPPATCH on the ``calendar-user-type``
        property.
        """
        try:
            return self._metadata().get_calendar_user_type()
        except KeyError:
            return scheduling.CALENDAR_USER_TYPE_INDIVIDUAL

    def set_calendar_user_type(self, cutype: str | None) -> None:
        """Persist the principal's calendar-user-type.

        Delegates to :class:`FileBasedCollectionMetadata` backed by
        the principal's ``.xandikos`` config file. ``None`` unsets
        the key, restoring the INDIVIDUAL default.
        """
        if cutype is not None and cutype not in scheduling.CALENDAR_USER_TYPES:
            raise ValueError(
                f"calendar-user-type must be one of "
                f"{', '.join(scheduling.CALENDAR_USER_TYPES)}, got {cutype!r}"
            )
        self._metadata().set_calendar_user_type(cutype)

    def get_schedule_default_calendar_url(self) -> str:
        """Return the principal-nominated default calendar URL.

        Reads from the principal's ``.xandikos`` config; raises
        :class:`KeyError` if the principal hasn't set one. The
        scheduling inbox falls back to auto-picking when no override
        is configured.
        """
        return self._metadata().get_schedule_default_calendar_url()

    def set_schedule_default_calendar_url(self, url: str | None) -> None:
        """Persist the principal's nominated default calendar URL.

        Delegates to :class:`FileBasedCollectionMetadata`. ``None``
        unsets the key and restores the inbox's auto-pick.
        """
        self._metadata().set_schedule_default_calendar_url(url)

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


class SingleUserFilesystemBackend(FilesystemBackend):
    def __init__(
        self,
        path,
        *,
        paranoid: bool = False,
        index_threshold: int | None = None,
        eager_indexing: bool = False,
        autocreate: bool = False,
        show_principals_on_root: bool = True,
        imip_transport: imip_transport_mod.IMIPTransport | None = None,
        imip_from: str | None = None,
        default_email: str | None = None,
    ) -> None:
        super().__init__(path)
        self._user_principals: set[str] = set()
        self.default_email = default_email
        self.paranoid = paranoid
        self.index_threshold = index_threshold
        self.eager_indexing = eager_indexing
        self.autocreate = autocreate
        self.show_principals_on_root = show_principals_on_root
        self.imip_transport: imip_transport_mod.IMIPTransport = (
            imip_transport
            if imip_transport is not None
            else imip_transport_mod.NullTransport()
        )
        self.imip_from = imip_from
        self._open_store = functools.lru_cache(maxsize=16)(self._open_store_uncached)

    def _open_store_uncached(self, path: str):
        """Open a store from a filesystem path, uncached."""
        return open_store_from_path(
            path,
            double_check_indexes=self.paranoid,
            index_threshold=self.index_threshold,
            eager_indexing=self.eager_indexing,
        )

    def _mark_as_principal(self, path):
        self._user_principals.add(posixpath.normpath(path))

    def create_collection(self, relpath):
        p = self._map_to_file_path(relpath)
        store = TreeGitStore.create(p)
        self._open_store.cache_clear()
        return Collection(self, relpath, store)

    def create_principal(self, relpath, create_defaults=False):
        principal = PrincipalBare.create(self, relpath)
        self._mark_as_principal(relpath)
        if create_defaults:
            create_principal_defaults(self, principal)

    def find_principals(self):
        """List all of the principals on this server."""
        return self._user_principals

    def get_principal(self, relpath: str) -> "Principal | None":
        relpath = posixpath.normpath(relpath)
        if relpath not in self._user_principals:
            return None
        # Defer to the regular get_resource path so the lookup picks up
        # whichever Principal subclass corresponds to the on-disk layout.
        r = self.get_resource(relpath)
        if isinstance(r, Principal):
            return r
        return None

    def get_resource(self, relpath):
        relpath = posixpath.normpath(relpath)
        if not relpath.startswith("/"):
            raise ValueError("relpath %r should start with /")
        if relpath == "/":
            return RootPage(self, show_principals=self.show_principals_on_root)
        p = self._map_to_file_path(relpath)
        if p is None:
            return None
        if os.path.isdir(p):
            try:
                store = self._open_store(p)
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


class XandikosApp(webdav.WebDAVApp):
    """A wsgi App that provides a Xandikos web server."""

    def __init__(
        self,
        backend,
        current_user_principal,
        strict=True,
        vapid_keystore: "webdav_push.VapidKeystore | None" = None,
        state_dir: str | None = None,
    ) -> None:
        super().__init__(backend, strict=strict)
        self.state_dir = state_dir

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
        if vapid_keystore is not None:
            assert state_dir is not None, (
                "state_dir is required when WebDAV-Push is enabled"
            )
            webdav_push.install(self, vapid_keystore, state_dir=state_dir)

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
        logger.info("Create calendar in %s.", resource.store.path)
    try:
        principal.get_schedule_default_calendar_url()
    except KeyError:
        principal.set_schedule_default_calendar_url("/" + calendar_path.lstrip("/"))
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
        logger.info("Create addressbook in %s.", resource.store.path)
    inbox_path = posixpath.join(principal.relpath, principal.get_schedule_inbox_url())
    try:
        resource = backend.create_collection(inbox_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_SCHEDULE_INBOX)
        logger.info("Create inbox in %s.", resource.store.path)


class RedirectDavHandler:
    def __init__(self, dav_root: str) -> None:
        self._dav_root = dav_root

    async def __call__(self, request):
        from aiohttp import web

        return web.HTTPFound(self._dav_root)


def _make_subscription_delete_handler(main_app: "XandikosApp"):
    """Build the aiohttp handler for ``DELETE ${prefix}/.subscriptions/<id>``."""
    from aiohttp import web

    async def handler(request):
        sub_id = request.match_info["sub_id"]
        # Mirror what WebDAVApp._handle_request does for REMOTE_USER so
        # check_access sees the authenticated principal.
        environ: dict = {"SCRIPT_NAME": ""}
        remote_user = request.headers.get("X-Remote-User")
        if remote_user and hasattr(main_app.backend, "set_principal"):
            environ["REMOTE_USER"] = remote_user
            main_app.backend.set_principal(remote_user)
        status, reason = await webdav_push.delete_subscription(
            main_app, environ, sub_id
        )
        return web.Response(status=status, reason=reason)

    return handler


def _maybe_mount_subscription_route(aiohttp_app, main_app: "XandikosApp") -> None:
    """Mount the WebDAV-Push DELETE route when push is enabled."""
    if webdav_push.FEATURE not in main_app.extra_features:
        return
    aiohttp_app.router.add_route(
        "DELETE",
        "/" + webdav_push.SUBSCRIPTION_ROUTE + "/{sub_id}",
        _make_subscription_delete_handler(main_app),
    )


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
            logger.error("Error registering %s: %s", service, e)

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
    backend = SingleUserFilesystemBackend(
        directory, default_email=os.environ.get("EMAIL")
    )
    backend._mark_as_principal(current_user_principal)

    if autocreate or defaults:
        if not os.path.isdir(directory):
            os.makedirs(directory)
        backend.create_principal(current_user_principal, create_defaults=defaults)

    if not os.path.isdir(directory):
        logger.warning(
            "%r does not exist. Run xandikos with --autocreate?",
            directory,
        )
    if not backend.get_resource(current_user_principal):
        logger.warning(
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
        logger.info("Listening on unix domain socket %s", socket_path)
    if listen_address and port:
        logger.info("Listening on %s:%s", listen_address, port)

    from aiohttp import web

    app = web.Application()
    for path in WELLKNOWN_DAV_PATHS:
        app.router.add_route("*", path, RedirectDavHandler(route_prefix).__call__)

    if route_prefix.strip("/"):
        xandikos_app = web.Application()
        _maybe_mount_subscription_route(xandikos_app, main_app)
        xandikos_app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

        async def redirect_to_subprefix(request):
            return web.HTTPFound(route_prefix)

        app.router.add_route("*", "/", redirect_to_subprefix)
        app.add_subapp(route_prefix, xandikos_app)
    else:
        _maybe_mount_subscription_route(app, main_app)
        app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

    web.run_app(app, port=port, host=listen_address, path=socket_path)


BASIC_AUTH_REALM = "Xandikos"


def basic_auth_middleware(htpasswd_file):
    """Build an aiohttp middleware enforcing HTTP Basic auth against htpasswd_file."""
    import binascii
    from aiohttp import web

    from . import htpasswd as htpasswd_mod

    def _unauthorized() -> web.Response:
        return web.Response(
            status=401,
            text="Authentication required.\n",
            headers={"WWW-Authenticate": f'Basic realm="{BASIC_AUTH_REALM}"'},
        )

    @web.middleware
    async def middleware(request, handler):
        header = request.headers.get("Authorization", "")
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return _unauthorized()
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return _unauthorized()
        username, _, password = decoded.partition(":")
        if not username:
            return _unauthorized()
        try:
            if not htpasswd_file.check(username, password):
                return _unauthorized()
        except htpasswd_mod.HtpasswdError as exc:
            logger.error("htpasswd check failed: %s", exc)
            return web.Response(status=500, text="Authentication misconfigured.\n")
        # Propagate the authenticated user to the WebDAV layer, which reads
        # X-Remote-User the same way it would behind a reverse proxy.
        new_request = request.clone(
            headers={**request.headers, "X-Remote-User": username}
        )
        return await handler(new_request)

    return middleware


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
        "--socket-mode",
        dest="socket_mode",
        default=None,
        help=(
            "File mode (permissions) for unix domain socket, "
            "in octal (e.g. 660). Only used when listening on a unix socket."
        ),
    )
    access_group.add_argument(
        "--socket-group",
        dest="socket_group",
        default=None,
        help=(
            "Group ownership for unix domain socket. "
            "Only used when listening on a unix socket."
        ),
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
    access_group.add_argument(
        "--autocert",
        action="store_true",
        help=(
            "Serve HTTPS using a self-signed certificate, generating one "
            "under <state-dir>/certs if missing. "
            "For development and testing only - do not use in production."
        ),
    )
    access_group.add_argument(
        "--htpasswd",
        dest="htpasswd",
        default=None,
        metavar="FILE",
        help=(
            "Require HTTP Basic authentication using credentials from the "
            "given Apache-style htpasswd file. bcrypt entries (htpasswd -B) "
            "are recommended. Requires --autocert: Basic auth sends "
            "credentials in cleartext and must not be served over plain "
            "HTTP. If you run Xandikos behind a reverse proxy, configure "
            "authentication there instead of using this flag."
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
    parser.add_argument(
        "--state-dir",
        dest="state_dir",
        default=None,
        metavar="DIR",
        help=(
            "Directory for Xandikos server state (TLS certificates, "
            "VAPID keys, ...). Distinct from --directory, which stores "
            "user calendars and address books. "
            "Defaults to $XDG_DATA_HOME/xandikos."
        ),
    )
    parser.add_argument(
        "--webdav-push",
        dest="webdav_push",
        action="store_true",
        help=(
            "Enable WebDAV-Push (draft-bitfire-webdav-push). A VAPID "
            "(RFC 8292) keypair is generated under <state-dir>/vapid/ "
            "on first start. Requires the 'webdav-push' optional "
            "dependencies."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Print debug messages")
    # Hidden arguments. These may change without notice in between releases,
    # and are generally just meant for developers.
    parser.add_argument("--paranoid", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--index-threshold", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--eager",
        action="store_true",
        help="Pre-populate indexes at startup for faster initial queries.",
    )

    imip_transport_mod.add_arguments(parser)
    imip_listen.add_arguments(parser)
    milter.add_listener_arguments(parser)


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

    backend = SingleUserFilesystemBackend(
        os.path.abspath(options.directory),
        paranoid=options.paranoid,
        index_threshold=options.index_threshold,
        eager_indexing=options.eager,
        imip_transport=imip_transport_mod.from_args(options),
        imip_from=options.smtp_from,
        default_email=os.environ.get("EMAIL"),
    )
    backend._mark_as_principal(options.current_user_principal)

    if options.autocreate or options.defaults:
        if not os.path.isdir(options.directory):
            os.makedirs(options.directory)
        backend.create_principal(
            options.current_user_principal, create_defaults=options.defaults
        )

    if not os.path.isdir(options.directory):
        logger.warning(
            "%r does not exist. Run xandikos with --autocreate?",
            options.directory,
        )
    if not backend.get_resource(options.current_user_principal):
        logger.warning(
            "default user principal %s does not exist. Run xandikos with --autocreate?",
            options.current_user_principal,
        )

    from .__main__ import _get_package_versions

    version_str = ", ".join(f"{pkg} {ver}" for pkg, ver in _get_package_versions())
    logger.info("%s", version_str)

    state_dir = options.state_dir or default_state_dir()

    vapid_keystore: webdav_push.VapidKeystore | None = None
    if options.webdav_push:
        try:
            vapid_keystore = webdav_push.VapidKeystore(os.path.join(state_dir, "vapid"))
            # Trigger key load/generation eagerly so misconfiguration
            # surfaces at startup rather than on the first PROPFIND.
            _ = vapid_keystore.public_key_b64
        except RuntimeError as exc:
            parser.error(str(exc))

    main_app = XandikosApp(
        backend,
        current_user_principal=options.current_user_principal,
        strict=options.strict,
        vapid_keystore=vapid_keystore,
        state_dir=state_dir,
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
        logger.info("Receiving file descriptors from systemd socket activation")
    elif "/" in options.listen_address:
        socket_path = options.listen_address
        listen_address = None
        listen_port = None  # otherwise aiohttp also listens on default host
        listen_socks = []
        logger.info("Listening on unix domain socket %s", socket_path)
    else:
        listen_address = options.listen_address
        listen_port = options.port
        socket_path = None
        listen_socks = []
        logger.info("Listening on %s:%s", listen_address, options.port)

    from aiohttp import web

    ssl_context = None
    if options.autocert:
        logger.warning(
            "--autocert is enabled. The generated certificate is self-signed "
            "and intended for development or testing only. Do NOT use this "
            "in production; instead, run Xandikos behind a reverse proxy "
            "(e.g. nginx, Apache, or Caddy) that terminates TLS using a "
            "certificate from a trusted CA such as Let's Encrypt."
        )
        if socket_path is not None:
            parser.error("--autocert cannot be combined with a unix domain socket")
        if listen_socks:
            parser.error("--autocert cannot be combined with systemd socket activation")
        from . import autocert as autocert_mod

        try:
            cert_path, key_path = autocert_mod.ensure_self_signed(
                os.path.join(state_dir, "certs"),
                hostname=listen_address or "localhost",
            )
        except RuntimeError as exc:
            parser.error(str(exc))
        ssl_context = autocert_mod.make_ssl_context(cert_path, key_path)

    htpasswd_file = None
    if options.htpasswd:
        if ssl_context is None:
            parser.error(
                "--htpasswd requires --autocert. Basic authentication sends "
                "credentials in cleartext and must not be served over plain "
                "HTTP. If you are running Xandikos behind a reverse proxy, "
                "configure authentication at the proxy instead."
            )
        from . import htpasswd as htpasswd_mod

        try:
            htpasswd_file = htpasswd_mod.HtpasswdFile(options.htpasswd)
        except htpasswd_mod.HtpasswdError as exc:
            parser.error(str(exc))
        logger.info(
            "HTTP Basic authentication enabled (htpasswd: %s)", options.htpasswd
        )

    if options.metrics_port == options.port:
        parser.error("Metrics port cannot be the same as the main port")

    app = web.Application()
    if options.metrics_port is not None:
        metrics_app = web.Application()
        try:
            from aiohttp_openmetrics import metrics, metrics_middleware
        except ModuleNotFoundError:
            logger.warning(
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
        if htpasswd_file is not None:
            xandikos_app.middlewares.append(basic_auth_middleware(htpasswd_file))
        _maybe_mount_subscription_route(xandikos_app, main_app)
        xandikos_app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

        async def redirect_to_subprefix(request):
            return web.HTTPFound(options.route_prefix)

        app.router.add_route("*", "/", redirect_to_subprefix)
        app.add_subapp(options.route_prefix, xandikos_app)
    else:
        if htpasswd_file is not None:
            app.middlewares.append(basic_auth_middleware(htpasswd_file))
        _maybe_mount_subscription_route(app, main_app)
        app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

    if options.avahi:
        try:
            import avahi  # noqa: F401
            import dbus  # noqa: F401
        except ImportError:
            logger.error(
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
        sites.append(
            web.TCPSite(runner, listen_address, listen_port, ssl_context=ssl_context)
        )

    import signal

    # Set up graceful shutdown handling
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info("Received signal %s, shutting down gracefully...", signum)
        # Use call_soon_threadsafe to safely set the event from signal handler
        loop.call_soon_threadsafe(shutdown_event.set)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    for site in sites:
        await site.start()

    imip_listener: imip_listen.Listener | None = None
    if options.imip_listen:
        try:
            import aiosmtpd  # noqa: F401
        except ImportError:
            parser.error(
                "--imip-listen requires the aiosmtpd package; "
                "install with: pip install 'xandikos[imip-listen]'"
            )
        try:
            target = imip_listen.parse_listen_target(options.imip_listen)
        except imip_listen.IMIPListenConfigError as exc:
            parser.error(str(exc))
        handler = imip_listen.IMIPLMTPHandler(backend, options.current_user_principal)
        try:
            imip_listener = await imip_listen.start_listener(
                target,
                handler,
                socket_mode=options.imip_listen_mode,
                socket_group=options.imip_listen_group,
            )
        except imip_listen.IMIPListenConfigError as exc:
            parser.error(str(exc))
        if isinstance(target, tuple):
            logger.info("Listening for iMIP on LMTP %s:%s", target[0], target[1])
        else:
            logger.info("Listening for iMIP on LMTP unix socket %s", target)

    milter_listener: milter.Listener | None = None
    if options.milter_listen:
        try:
            milter_target = milter.parse_listen_target(options.milter_listen)
        except milter.IMIPListenConfigError as exc:
            parser.error(str(exc))
        milter_handler = milter.MilterHandler(
            milter.InProcessTransport(backend, options.current_user_principal)
        )
        try:
            milter_listener = await milter.start_listener(
                milter_target,
                milter_handler,
                socket_mode=options.milter_listen_mode,
                socket_group=options.milter_listen_group,
            )
        except milter.IMIPListenConfigError as exc:
            parser.error(str(exc))
        if isinstance(milter_target, tuple):
            logger.info(
                "Listening for milter on %s:%s", milter_target[0], milter_target[1]
            )
        else:
            logger.info("Listening for milter on unix socket %s", milter_target)

    # Set socket group ownership after the socket is created
    if socket_path and options.socket_group is not None:
        import grp

        try:
            gid = grp.getgrnam(options.socket_group).gr_gid
            os.chown(socket_path, -1, gid)
            logger.info("Set socket group to %s", options.socket_group)
        except KeyError:
            parser.error(f"Unknown group: {options.socket_group}")
        except OSError as e:
            logger.error("Failed to set socket group: %s", e)

    # Set socket permissions after the socket is created
    if socket_path and options.socket_mode is not None:
        try:
            mode = int(options.socket_mode, 8)
            os.chmod(socket_path, mode)
            logger.info("Set socket permissions to %s", options.socket_mode)
        except ValueError:
            parser.error(f"Invalid socket mode: {options.socket_mode}")
        except OSError as e:
            logger.error("Failed to set socket permissions: %s", e)

    # Wait for shutdown signal
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down gracefully...")

    # Cleanup: stop all sites and runners
    logger.info("Stopping web servers...")
    for site in sites:
        await site.stop()

    if imip_listener is not None:
        await imip_listener.stop()

    if milter_listener is not None:
        await milter_listener.stop()

    await runner.cleanup()
    if metrics_app:
        await metrics_runner.cleanup()

    logger.info("Shutdown complete.")


if __name__ == "__main__":
    import sys

    # Alias so siblings doing ``from . import web`` get the same module
    # object, not a second copy with distinct classes.
    sys.modules["xandikos.web"] = sys.modules["__main__"]

    import argparse

    parser = argparse.ArgumentParser(usage="%(prog)s [options]")
    add_parser(parser)
    args = parser.parse_args(sys.argv[1:])

    sys.exit(asyncio.run(main(args, parser)))
