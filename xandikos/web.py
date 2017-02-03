# Xandikos
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
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

import functools
import mimetypes
import os
import posixpath
import uuid

from xandikos import access, caldav, carddav, sync, webdav, infit
from xandikos.store import (
    BareGitStore,
    GitStore,
    NotStoreError,
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_OTHER,
    )

WELLKNOWN_DAV_PATHS = set([caldav.WELLKNOWN_CALDAV_PATH, carddav.WELLKNOWN_CARDDAV_PATH])

RESOURCE_CACHE_SIZE = 128
# TODO(jelmer): Make these configurable/dynamic
CALENDAR_HOME = 'calendars'
ADDRESSBOOK_HOME = 'contacts'
USER_ADDRESS_SET = ['mailto:jelmer@jelmer.uk']

ROOT_PAGE_CONTENTS = b"""\
<html>
  <body>
    This is a Xandikos WebDAV server. See
    <a href="https://github.com/jelmer/xandikos">
    https://github.com/jelmer/xandikos</a>.
  </body>
</html>"""


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

    def __init__(self, store, name, etag, content_type):
        self.store = store
        self.name = name
        self.etag = etag
        self.content_type = content_type
        self._chunked = None

    def __repr__(self):
        return "%s(%r, %r, %r, %r)" % (
            type(self).__name__, self.store, self.name, self.etag,
             self.content_type)

    def get_body(self):
        if self._chunked is None:
            self._chunked = self.store.get_raw(self.name, self.etag)
        return self._chunked

    def set_body(self, data, replace_etag=None):
        etag = self.store.import_one(
            self.name, b''.join(data), extract_strong_etag(replace_etag))
        return create_strong_etag(etag)

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


class StoreBasedCollection(object):

    def __init__(self, store):
        self.store = store

    def _get_resource(self, name, etag):
        return ObjectResource(
            self.store, name, etag, self._object_content_type)

    def get_displayname(self):
        displayname = self.store.get_displayname()
        if displayname is None:
            return os.path.basename(self.store.repo.path)
        return displayname

    def get_sync_token(self):
        return self.store.get_ctag()

    def get_ctag(self):
        return self.store.get_ctag()

    def get_etag(self):
        return create_strong_etag(self.store.get_ctag())

    def members(self):
        ret = []
        for (name, etag) in self.store.iter_with_etag():
            resource = self._get_resource(name, etag)
            ret.append((name, resource))
        return ret

    def get_member(self, name):
        assert name != ''
        for (fname, fetag) in self.store.iter_with_etag():
            if name == fname:
                return self._get_resource(name, fetag)
        else:
            raise KeyError(name)

    def delete_member(self, name, etag=None):
        self.store.delete_one(name, extract_strong_etag(etag))

    def create_member(self, name, contents, content_type):
        if name is None:
            name = str(uuid.uuid4()) + mimetypes.get_extension(content_type)
        etag = self.store.import_one(name, b''.join(contents))
        return create_strong_etag(etag)

    def iter_differences_since(self, old_token, new_token):
        for (name, old_etag, new_etag) in self.store.iter_changes(
                old_token, new_token):
            if old_etag is not None:
                old_resource = self._get_resource(name, old_etag)
            else:
                old_resource = None
            if new_etag is not None:
                new_resource = self._get_resource(name, new_etag)
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


class Collection(StoreBasedCollection,caldav.Calendar):
    """A generic WebDAV collection."""

    _object_content_type = 'application/unknown'

    def __init__(self, store):
        self.store = store


class CalendarResource(StoreBasedCollection,caldav.Calendar):

    _object_content_type = 'text/calendar'

    def get_calendar_description(self):
        return self.store.get_description()

    def get_calendar_color(self):
        color = self.store.get_color()
        if not color:
            raise KeyError
        if color and color[0] != '#':
            color = '#' + color
        return color

    def get_calendar_timezone(self):
        # TODO(jelmer): Read a magic file from the store?
        raise KeyError

    def set_calendar_timezone(self, content):
        raise NotImplementedError(self.set_calendar_timezone)

    def get_supported_calendar_components(self):
        return ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY"]

    def get_supported_calendar_data_types(self):
        return [('text/calendar', '1.0'),
                ('text/calendar', '2.0')]

    def get_content_type(self):
        # TODO
        raise KeyError

    def get_max_date_time(self):
        return "99991231T235959Z"

    def get_min_date_time(self):
        return "00010101T000000Z"


class AddressbookResource(StoreBasedCollection,carddav.Addressbook):

    _object_content_type = 'text/vcard'

    def get_content_type(self):
        # TODO
        raise KeyError

    def get_addressbook_description(self):
        return self.store.get_description()

    def get_supported_address_data_types(self):
        return [('text/vcard', '3.0')]

    def get_max_resource_size(self):
        # No resource limit
        raise KeyError

    def get_max_image_size(self):
        # No resource limit
        raise KeyError

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

    def get_displayname(self):
        return posixpath.basename(self.relpath)

    def get_sync_token(self):
        raise KeyError

    def get_etag(self):
        raise KeyError

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def members(self):
        ret = []
        p = self.backend._map_to_file_path(self.relpath)
        for name in os.listdir(p):
            if name.startswith('.'):
                continue
            resource = self.get_member(name)
            ret.append((name, resource))
        return ret

    def create_collection(self, name):
        relpath = posixpath.join(self.relpath, name)
        p = self.backend._map_to_file_path(relpath)
        # Why bare store, not a tree store?
        return BareGitStore.create(p)

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


class RootPage(webdav.Resource):
    """A non-DAV resource."""

    resource_types = []

    def get_body(self):
        return [ROOT_PAGE_CONTENTS]

    def get_content_length(self):
        return len(b''.join(self.get_body()))

    def get_content_type(self):
        return 'text/html'

    def get_supported_locks(self):
        return []

    def get_active_locks(self):
        return []

    def get_etag(self):
        return '"root-page"'


class Principal(CollectionSetResource):
    """Principal user resource."""

    resource_types = webdav.Collection.resource_types + [webdav.PRINCIPAL_RESOURCE_TYPE]

    def get_principal_url(self):
        return self.path

    def get_calendar_home_set(self):
        return [CALENDAR_HOME]

    def get_addressbook_home_set(self):
        return [ADDRESSBOOK_HOME]

    def get_calendar_user_address_set(self):
        return USER_ADDRESS_SET

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



@functools.lru_cache(maxsize=RESOURCE_CACHE_SIZE)
def open_store_from_path(path):
    return GitStore.open_from_path(path)


class XandikosBackend(webdav.Backend):

    def __init__(self, path, current_user_principal):
        self.path = path
        self.current_user_principal = posixpath.normpath(current_user_principal)

    def _map_to_file_path(self, relpath):
        return os.path.join(self.path, relpath.lstrip('/'))

    def get_resource(self, relpath):
        relpath = posixpath.normpath(relpath)
        if relpath == '/':
            return RootPage()
        elif relpath == self.current_user_principal:
            return Principal(self, relpath)
        p = self._map_to_file_path(relpath)
        if p is None:
            return None
        if os.path.isdir(p):
            try:
                store = open_store_from_path(p)
            except NotStoreError:
                return CollectionSetResource(self, relpath)
            else:
                return {STORE_TYPE_CALENDAR: CalendarResource,
                        STORE_TYPE_ADDRESSBOOK: AddressbookResource,
                        STORE_TYPE_OTHER: Collection}[store.get_type()](store)
        else:
            (basepath, name) = os.path.split(relpath)
            assert name != '', 'path is %r' % relpath
            store = self.get_resource(basepath)
            if (store is None or
                webdav.COLLECTION_RESOURCE_TYPE not in store.resource_types):
                return None
            try:
                return store.get_member(name)
            except KeyError:
                return None


class XandikosApp(webdav.WebDAVApp):
    """A wsgi App that provides a Xandikos web server.
    """

    def __init__(self, path, current_user_principal):
        super(XandikosApp, self).__init__(XandikosBackend(
            path, current_user_principal))
        self.register_properties([
            webdav.ResourceTypeProperty(),
            webdav.CurrentUserPrincipalProperty(
                current_user_principal),
            webdav.PrincipalURLProperty(),
            webdav.DisplayNameProperty(),
            webdav.GetETagProperty(),
            webdav.GetContentTypeProperty(),
            caldav.CalendarHomeSetProperty(),
            caldav.CalendarUserAddressSetProperty(),
            carddav.AddressbookHomeSetProperty(),
            caldav.CalendarDescriptionProperty(),
            caldav.CalendarColorProperty(),
            caldav.SupportedCalendarComponentSetProperty(),
            carddav.AddressbookDescriptionProperty(),
            carddav.PrincipalAddressProperty(),
            webdav.GetCTagProperty(),
            carddav.SupportedAddressDataProperty(),
            webdav.SupportedReportSetProperty(self.reporters),
            sync.SyncTokenProperty(),
            caldav.SupportedCalendarDataProperty(),
            caldav.CalendarTimezoneProperty(),
            caldav.MinDateTimeProperty(),
            caldav.MaxDateTimeProperty(),
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
            ])
        self.register_reporters([
            caldav.CalendarMultiGetReporter(),
            caldav.CalendarQueryReporter(),
            carddav.AddressbookMultiGetReporter(),
            webdav.ExpandPropertyReporter(),
            sync.SyncCollectionReporter(),
            caldav.FreeBusyQueryReporter(),
            ])


class WellknownRedirector(object):

    def __init__(self, inner_app):
        self._inner_app = inner_app

    def __call__(self, environ, start_response):
        # See https://tools.ietf.org/html/rfc6764
        if ((environ['SCRIPT_NAME'] + environ['PATH_INFO'])
                in WELLKNOWN_DAV_PATHS):
            start_response('302 Found', [
                ('Location', options.dav_root)])
            return []
        return self._inner_app(environ, start_response)


if __name__ == '__main__':
    import optparse
    import sys
    parser = optparse.OptionParser()
    parser.usage = "%prog -d ROOT-DIR [OPTIONS]"
    parser.add_option("-l", "--listen_address", dest="listen_address",
                      default="localhost",
                      help="Binding IP address.")
    parser.add_option("-d", "--directory", dest="directory",
                      default=None,
                      help="Default path to serve from.")
    parser.add_option("-p", "--port", dest="port", type=int,
                      default=8000,
                      help="Port to listen on.")
    parser.add_option("--current-user-principal",
                      default="/user/",
                      help="Path to current user principal.")
    parser.add_option("--dav-root",
                      default="/",
                      help="Path to DAV root.")
    options, args = parser.parse_args(sys.argv)

    if options.directory is None:
        parser.print_usage()
        sys.exit(1)

    app = XandikosApp(
        options.directory,
        current_user_principal=options.current_user_principal)

    from wsgiref.simple_server import make_server
    app = WellknownRedirector(app)
    server = make_server(options.listen_address, options.port, app)
    server.serve_forever()
