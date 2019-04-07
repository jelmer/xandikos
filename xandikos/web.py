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

from email.utils import parseaddr
import functools
import hashlib
import jinja2
import logging
import os
import posixpath
import shutil
import urllib.parse

from xandikos import __version__ as xandikos_version
from xandikos import (access, apache, caldav, carddav, quota, sync, webdav,
                      infit, scheduling, timezones)
from xandikos.icalendar import (
    ICalendarFile,
    CalendarFilter,
)
from xandikos.store import (
    DuplicateUidError,
    InvalidFileContents,
    NoSuchItem,
    NotStoreError,
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_PRINCIPAL,
    STORE_TYPE_SCHEDULE_INBOX,
    STORE_TYPE_SCHEDULE_OUTBOX,
    STORE_TYPE_OTHER,
)
from xandikos.store.git import (
    GitStore,
    TreeGitStore,
)
from xandikos.vcard import VCardFile


WELLKNOWN_DAV_PATHS = {caldav.WELLKNOWN_CALDAV_PATH,
                       carddav.WELLKNOWN_CARDDAV_PATH}

STORE_CACHE_SIZE = 128
# TODO(jelmer): Make these configurable/dynamic
CALENDAR_HOME_SET = ['calendars']
ADDRESSBOOK_HOME_SET = ['contacts']

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATES_DIR))


def render_jinja_page(name, accepted_content_languages, **kwargs):
    """Render a HTML page from jinja template.

    :param name: Name of the page
    :param accepted_content_languages: List of accepted content languages
    :return: TUple of (body, content_length, etag, content_type, languages)
    """
    # TODO(jelmer): Support rendering other languages
    encoding = 'utf-8'
    template = jinja_env.get_template(name)
    body = template.render(
        version=xandikos_version,
        urljoin=urllib.parse.urljoin, **kwargs).encode(encoding)
    return ([body], len(body), None, 'text/html; encoding=%s' % encoding,
            ['en-UK'])


def create_strong_etag(etag):
    """Create strong etags.

    :param etag: basic etag
    :return: A strong etag
    """
    return '"' + etag + '"'


def extract_strong_etag(etag):
    """Extract a strong etag from a string."""
    if etag is None:
        return etag
    return etag.strip('"')


class ObjectResource(webdav.Resource):
    """Object resource."""

    def __init__(self, store, name, content_type, etag, file=None):
        self.store = store
        self.name = name
        self.etag = etag
        self.content_type = content_type
        self._file = file

    def __repr__(self):
        return "%s(%r, %r, %r, %r)" % (
            type(self).__name__, self.store, self.name, self.etag,
            self.get_content_type()
        )

    @property
    def file(self):
        if self._file is None:
            self._file = self.store.get_file(self.name, self.content_type,
                                             self.etag)
        return self._file

    def get_body(self):
        return self.file.content

    def set_body(self, data, replace_etag=None):
        try:
            (name, etag) = self.store.import_one(
                self.name, self.content_type, data,
                replace_etag=extract_strong_etag(replace_etag))
        except InvalidFileContents as e:
            # TODO(jelmer): Not every invalid file is a calendar file..
            raise webdav.PreconditionFailure(
                '{%s}valid-calendar-data' % caldav.NAMESPACE,
                'Not a valid calendar file: %s' % e.error)
        except DuplicateUidError:
            raise webdav.PreconditionFailure(
                '{%s}no-uid-conflict' % caldav.NAMESPACE,
                'UID already in use.')
        return create_strong_etag(etag)

    def get_content_language(self):
        raise KeyError

    def get_content_type(self):
        return self.content_type

    def get_content_length(self):
        return sum(map(len, self.get_body()))

    def get_etag(self):
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


class StoreBasedCollection(object):

    def __init__(self, backend, relpath, store):
        self.backend = backend
        self.relpath = relpath
        self.store = store

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.store)

    def set_resource_types(self, resource_types):
        # TODO(jelmer): Allow more than just this set; allow combining
        # addressbook/calendar.
        resource_types = set(resource_types)
        if resource_types == {caldav.CALENDAR_RESOURCE_TYPE,
                              webdav.COLLECTION_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_CALENDAR)
        elif resource_types == {carddav.ADDRESSBOOK_RESOURCE_TYPE,
                                webdav.COLLECTION_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_ADDRESSBOOK)
        elif resource_types == {webdav.PRINCIPAL_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_PRINCIPAL)
        elif resource_types == {caldav.SCHEDULE_INBOX_RESOURCE_TYPE,
                                webdav.COLLECTION_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_SCHEDULE_INBOX)
        elif resource_types == {caldav.SCHEDULE_OUTBOX_RESOURCE_TYPE,
                                webdav.COLLECTION_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_SCHEDULE_OUTBOX)
        elif resource_types == {webdav.COLLECTION_RESOURCE_TYPE}:
            self.store.set_type(STORE_TYPE_OTHER)
        else:
            raise NotImplementedError(self.set_resource_types)

    def _get_resource(self, name, content_type, etag, file=None):
        return ObjectResource(self.store, name, content_type, etag, file=file)

    def _get_subcollection(self, name):
        return self.backend.get_resource(posixpath.join(self.relpath, name))

    def get_displayname(self):
        displayname = self.store.get_displayname()
        if displayname is None:
            return os.path.basename(self.store.repo.path)
        return displayname

    def set_displayname(self, displayname):
        self.store.set_displayname(displayname)

    def get_sync_token(self):
        return self.store.get_ctag()

    def get_ctag(self):
        return self.store.get_ctag()

    def get_etag(self):
        return create_strong_etag(self.store.get_ctag())

    def members(self):
        for (name, content_type, etag) in self.store.iter_with_etag():
            resource = self._get_resource(name, content_type, etag)
            yield (name, resource)
        for (name, resource) in self.subcollections():
            yield (name, resource)

    def subcollections(self):
        for name in self.store.subdirectories():
            yield (name, self._get_subcollection(name))

    def get_member(self, name):
        assert name != ''
        for (fname, content_type, fetag) in self.store.iter_with_etag():
            if name == fname:
                return self._get_resource(name, content_type, fetag)
        if name in self.store.subdirectories():
            return self._get_subcollection(name)
        raise KeyError(name)

    def delete_member(self, name, etag=None):
        assert name != ''
        try:
            self.store.delete_one(name, etag=extract_strong_etag(etag))
        except NoSuchItem:
            # TODO: Properly allow removing subcollections
            # self.get_subcollection(name).destroy()
            shutil.rmtree(os.path.join(self.store.path, name))

    def create_member(self, name, contents, content_type):
        try:
            (name, etag) = self.store.import_one(name, content_type, contents)
        except InvalidFileContents as e:
            # TODO(jelmer): Not every invalid file is a calendar file..
            raise webdav.PreconditionFailure(
                '{%s}valid-calendar-data' % caldav.NAMESPACE,
                'Not a valid calendar file: %s' % e.error)
        except DuplicateUidError:
            raise webdav.PreconditionFailure(
                '{%s}no-uid-conflict' % caldav.NAMESPACE,
                'UID already in use.')
        return (name, create_strong_etag(etag))

    def iter_differences_since(self, old_token, new_token):
        for (name, content_type,
             old_etag, new_etag) in self.store.iter_changes(
                 old_token, new_token):
            if old_etag is not None:
                old_resource = self._get_resource(name, content_type, old_etag)
            else:
                old_resource = None
            if new_etag is not None:
                new_resource = self._get_resource(name, content_type, new_etag)
            else:
                new_resource = None
            yield (name, old_resource, new_resource)

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
        return 'httpd/unix-directory'

    def get_content_language(self):
        raise KeyError

    def get_content_length(self):
        raise KeyError

    def destroy(self):
        # RFC2518, section 8.6.2 says this should recursively delete.
        self.store.destroy()

    def get_body(self):
        raise NotImplementedError(self.get_body)

    def render(self, self_url, accepted_content_types,
               accepted_content_languages):
        content_types = webdav.pick_content_types(
            accepted_content_types, ['text/html'])
        assert content_types == ['text/html']
        return render_jinja_page(
            'collection.html', accepted_content_languages, collection=self,
            self_url=self_url)

    def get_is_executable(self):
        return False

    def get_quota_used_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_quota_available_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_refreshrate(self):
        # TODO(jelmer): Support setting refreshrate
        raise KeyError

    def set_refreshrate(self, value):
        # TODO(jelmer): Store refreshrate
        raise NotImplementedError(self.set_refreshrate)


class Collection(StoreBasedCollection, webdav.Collection):
    """A generic WebDAV collection."""


class ScheduleInbox(StoreBasedCollection, scheduling.ScheduleInbox):
    """A schedling inbox collection."""


class ScheduleOutbox(StoreBasedCollection, scheduling.ScheduleOutbox):
    """A schedling outbox collection."""


class CalendarCollection(StoreBasedCollection, caldav.Calendar):

    def get_calendar_description(self):
        return self.store.get_description()

    def get_calendar_color(self):
        color = self.store.get_color()
        if not color:
            raise KeyError
        if color and color[0] != '#':
            color = '#' + color
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
        # TODO(jelmer): Read from config
        raise KeyError

    def set_calendar_timezone(self, content):
        raise NotImplementedError(self.set_calendar_timezone)

    def get_supported_calendar_components(self):
        return ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY"]

    def get_supported_calendar_data_types(self):
        return [('text/calendar', '1.0'),
                ('text/calendar', '2.0')]

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
        for (name, file, etag) in self.store.iter_with_filter(
                filter=filter):
            resource = self._get_resource(
                name, file.content_type, etag, file=file)
            yield (name, resource)


class AddressbookCollection(StoreBasedCollection, carddav.Addressbook):

    def get_addressbook_description(self):
        return self.store.get_description()

    def set_addressbook_description(self, description):
        self.store.set_description(description)

    def get_supported_address_data_types(self):
        return [('text/vcard', '3.0')]

    def get_max_resource_size(self):
        # No resource limit
        raise KeyError

    def get_max_image_size(self):
        # No resource limit
        raise KeyError

    def set_addressbook_color(self, color):
        self.store.set_color(color)

    def get_addressbook_color(self):
        color = self.store.get_color()
        if not color:
            raise KeyError
        if color and color[0] != '#':
            color = '#' + color
        return color


class CollectionSetResource(webdav.Collection):
    """Resource for calendar sets."""

    def __init__(self, backend, relpath):
        self.backend = backend
        self.relpath = relpath

    @classmethod
    def create(cls, backend, relpath):
        path = backend._map_to_file_path(relpath)
        if not os.path.isdir(path):
            os.makedirs(path)
            logging.info('Creating %s', path)
        return cls(backend, relpath)

    def get_displayname(self):
        return posixpath.basename(self.relpath)

    def get_sync_token(self):
        raise KeyError

    def get_etag(self):
        raise KeyError

    def get_ctag(self):
        raise KeyError

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def members(self):
        p = self.backend._map_to_file_path(self.relpath)
        for name in os.listdir(p):
            if name.startswith('.'):
                continue
            resource = self.get_member(name)
            yield (name, resource)

    def get_member(self, name):
        assert name != ''
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
        return 'httpd/unix-directory'

    def get_content_language(self):
        raise KeyError

    def get_content_length(self):
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

    def render(self, self_url, accepted_content_types,
               accepted_content_languages):
        content_types = webdav.pick_content_types(
            accepted_content_types, ['text/html'])
        assert content_types == ['text/html']
        return render_jinja_page(
            'root.html', accepted_content_languages, self_url=self_url)

    def get_is_executable(self):
        return False

    def get_quota_used_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError

    def get_quota_available_bytes(self):
        # TODO(jelmer): Ask the store?
        raise KeyError


class RootPage(webdav.Resource):
    """A non-DAV resource."""

    resource_types = []

    def __init__(self, backend):
        self.backend = backend

    def render(self, self_url, accepted_content_types,
               accepted_content_languages):
        content_types = webdav.pick_content_types(
            accepted_content_types, ['text/html'])
        assert content_types == ['text/html']
        return render_jinja_page(
            'root.html', accepted_content_languages,
            principals=self.backend.find_principals(),
            self_url=self_url)

    def get_body(self):
        raise KeyError

    def get_content_length(self):
        raise KeyError

    def get_content_type(self):
        return 'text/html'

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def get_etag(self):
        h = hashlib.md5()
        for c in self.get_body():
            h.update(c)
        return h.hexdigest()

    def get_last_modified(self):
        raise KeyError

    def get_content_language(self):
        return ['en-UK']

    def get_member(self, name):
        return self.backend.get_resource(name)

    def delete_member(self, name, etag=None):
        # This doesn't have any non-collection members.
        self.get_member(name).destroy()

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
        return '.'

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
            (fullname, email) = parseaddr(os.environ['EMAIL'])
        except KeyError:
            pass
        else:
            ret.append('mailto:' + email)
        return ret

    def set_infit_settings(self, settings):
        relpath = posixpath.join(self.relpath, '.infit')
        p = self.backend._map_to_file_path(relpath)
        with open(p, 'w') as f:
            f.write(settings)

    def get_infit_settings(self):
        relpath = posixpath.join(self.relpath, '.infit')
        p = self.backend._map_to_file_path(relpath)
        if not os.path.exists(p):
            raise KeyError
        with open(p, 'r') as f:
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
        return 'inbox'

    def get_creationdate(self):
        raise KeyError


class PrincipalBare(CollectionSetResource, Principal):
    """Principal user resource."""

    resource_types = [webdav.PRINCIPAL_RESOURCE_TYPE]

    @classmethod
    def create(cls, backend, relpath):
        p = super(PrincipalBare, cls).create(backend, relpath)
        to_create = set()
        to_create.update(p.get_addressbook_home_set())
        to_create.update(p.get_calendar_home_set())
        for n in to_create:
            try:
                backend.create_collection(posixpath.join(relpath, n))
            except FileExistsError:
                pass
        return p

    def render(self, self_url, accepted_content_types,
               accepted_content_languages):
        content_types = webdav.pick_content_types(
            accepted_content_types, ['text/html'])
        assert content_types == ['text/html']
        return render_jinja_page(
            'principal.html', accepted_content_languages, principal=self,
            self_url=self_url)

    def subcollections(self):
        # TODO(jelmer): Return members
        return []


class PrincipalCollection(Collection, Principal):
    """Principal user resource."""

    resource_types = (webdav.Collection.resource_types +
                      [webdav.PRINCIPAL_RESOURCE_TYPE])

    @classmethod
    def create(cls, backend, relpath):
        p = super(PrincipalCollection, cls).create(backend, relpath)
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
def open_store_from_path(path):
    store = GitStore.open_from_path(path)
    store.load_extra_file_handler(ICalendarFile)
    store.load_extra_file_handler(VCardFile)
    return store


class XandikosBackend(webdav.Backend):

    def __init__(self, path):
        self.path = path
        self._user_principals = set()

    def _map_to_file_path(self, relpath):
        return os.path.join(self.path, relpath.lstrip('/'))

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
        if relpath == '/':
            return RootPage(self)
        p = self._map_to_file_path(relpath)
        if p is None:
            return None
        if os.path.isdir(p):
            try:
                store = open_store_from_path(p)
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
                    STORE_TYPE_OTHER: Collection
                }[store.get_type()](self, relpath, store)
        else:
            (basepath, name) = os.path.split(relpath)
            assert name != '', 'path is %r' % relpath
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
    """A wsgi App that provides a Xandikos web server.
    """

    def __init__(self, backend, current_user_principal):
        super(XandikosApp, self).__init__(backend)

        def get_current_user_principal(env):
            try:
                return current_user_principal % env
            except KeyError:
                return None
        self.register_properties([
            webdav.ResourceTypeProperty(),
            webdav.CurrentUserPrincipalProperty(
                get_current_user_principal),
            webdav.PrincipalURLProperty(),
            webdav.DisplayNameProperty(),
            webdav.GetETagProperty(),
            webdav.GetContentTypeProperty(),
            webdav.GetContentLengthProperty(),
            webdav.GetContentLanguageProperty(),
            caldav.CalendarHomeSetProperty(),
            carddav.AddressbookHomeSetProperty(),
            caldav.CalendarDescriptionProperty(),
            caldav.CalendarColorProperty(),
            caldav.CalendarOrderProperty(),
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
        ])
        self.register_reporters([
            caldav.CalendarMultiGetReporter(),
            caldav.CalendarQueryReporter(),
            carddav.AddressbookMultiGetReporter(),
            carddav.AddressbookQueryReporter(),
            webdav.ExpandPropertyReporter(),
            sync.SyncCollectionReporter(),
            caldav.FreeBusyQueryReporter(),
        ])
        self.register_methods([
            caldav.MkcalendarMethod(),
        ])


class WellknownRedirector(object):
    """Redirect paths under .well-known/ to the appropriate paths."""

    def __init__(self, inner_app, dav_root):
        self._inner_app = inner_app
        self._dav_root = dav_root

    def __call__(self, environ, start_response):
        # See https://tools.ietf.org/html/rfc6764
        path = posixpath.normpath(
            environ['SCRIPT_NAME'] + environ['PATH_INFO'])
        if path in WELLKNOWN_DAV_PATHS:
            start_response('302 Found', [
                ('Location', self._dav_root)])
            return []
        return self._inner_app(environ, start_response)


def create_principal_defaults(backend, principal):
    """Create default calendar and addressbook for a principal.

    :param backend: Backend in which the principal exists.
    :param principal: Principal object
    """
    calendar_path = posixpath.join(principal.relpath,
                                   principal.get_calendar_home_set()[0],
                                   'calendar')
    try:
        resource = backend.create_collection(calendar_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_CALENDAR)
        logging.info('Create calendar in %s.', resource.store.path)
    addressbook_path = posixpath.join(principal.relpath,
                                      principal.get_addressbook_home_set()[0],
                                      'addressbook')
    try:
        resource = backend.create_collection(addressbook_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_ADDRESSBOOK)
        logging.info('Create addressbook in %s.', resource.store.path)
    calendar_path = posixpath.join(principal.relpath,
                                   principal.get_schedule_inbox_url())
    try:
        resource = backend.create_collection(calendar_path)
    except FileExistsError:
        pass
    else:
        resource.store.set_type(STORE_TYPE_SCHEDULE_INBOX)
        logging.info('Create inbox in %s.', resource.store.path)


def main(argv):
    import argparse
    import sys
    from xandikos import __version__
    parser = argparse.ArgumentParser(
        usage="%(prog)s -d ROOT-DIR [OPTIONS]",
        prog=argv[0])

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s ' + '.'.join(map(str, __version__)))

    access_group = parser.add_argument_group(title="Access Options")
    access_group.add_argument(
        "-l", "--listen_address", dest="listen_address", default="localhost",
        help="Binding IP address. [%(default)s]")
    access_group.add_argument(
        "-p", "--port", dest="port", type=int, default=8080,
        help="Port to listen on. [%(default)s]")
    access_group.add_argument(
        "--route-prefix", default="/", help=(
            "Path to Xandikos. "
            "(useful when Xandikos is behind a reverse proxy) "
            "[%(default)s]"))
    parser.add_argument(
        "-d", "--directory", dest="directory", default=None,
        help="Directory to serve from.")
    parser.add_argument(
        "--current-user-principal", default="/user/",
        help="Path to current user principal. [%(default)s]")
    parser.add_argument(
        "--autocreate", action="store_true", dest="autocreate",
        help="Automatically create necessary directories.")
    parser.add_argument(
        "--defaults", action="store_true", dest="defaults",
        help=("Create initial calendar and address book. "
              "Implies --autocreate."))
    parser.add_argument(
        "--dump-dav-xml", action="store_true", dest="dump_dav_xml",
        help="Print DAV XML request/responses.")
    options = parser.parse_args(argv[1:])

    if options.directory is None:
        parser.print_usage()
        sys.exit(1)

    if options.dump_dav_xml:
        # TODO(jelmer): Find a way to propagate this without abusing
        # os.environ.
        os.environ["XANDIKOS_DUMP_DAV_XML"] = "1"

    logging.basicConfig(level=logging.INFO)

    backend = XandikosBackend(options.directory)
    backend._mark_as_principal(options.current_user_principal)

    if options.autocreate or options.defaults:
        if not os.path.isdir(options.directory):
            os.makedirs(options.directory)
        backend.create_principal(
            options.current_user_principal,
            create_defaults=options.defaults)

    if not os.path.isdir(options.directory):
        logging.warning(
            '%r does not exist. Run xandikos with --autocreate?',
            options.directory)
    if not backend.get_resource(options.current_user_principal):
        logging.warning(
            'default user principal %s does not exist. '
            'Run xandikos with --autocreate?',
            options.current_user_principal)

    app = XandikosApp(
        backend,
        current_user_principal=options.current_user_principal)

    from wsgiref.simple_server import make_server
    app = WellknownRedirector(app, options.route_prefix)
    server = make_server(options.listen_address, options.port, app)
    logging.info('Listening on %s:%s', options.listen_address,
                 options.port)

    import signal
    # Set SIGINT to default handler; this appears to be necessary
    # when running under coverage.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    else:
        server.shutdown()


if __name__ == '__main__':
    import sys
    main(sys.argv)
