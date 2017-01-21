# Dystros
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

import os
import posixpath

from dystros import caldav, carddav, webdav
from dystros.store import (
    GitStore,
    NotStoreError,
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_OTHER,
    )

WELLKNOWN_DAV_PATHS = set([caldav.WELLKNOWN_CALDAV_PATH, carddav.WELLKNOWN_CARDDAV_PATH])

# TODO(jelmer): Make these configurable/dynamic
CALENDAR_HOME = 'calendars'
ADDRESSBOOK_HOME = 'contacts'
USER_ADDRESS_SET = ['mailto:jelmer@jelmer.uk']


class NonDAVResource(webdav.DAVResource):
    """A non-DAV resource."""

    resource_types = []

    def get_body(self):
        return []

    def get_etag(self):
        return "empty"


class ObjectResource(webdav.DAVResource):
    """Object resource."""

    def __init__(self, store, name, etag, content_type):
        self.store = store
        self.name = name
        self.etag = etag
        self.content_type = content_type

    def get_body(self):
        return [self.store.get_raw(self.name, self.etag)]

    def set_body(self, data, replace_etag=None):
        self.store.import_one(self.name, b''.join(data), replace_etag)

    def get_content_type(self):
        return self.content_type

    def get_etag(self):
        return self.etag


class StoreBasedCollection(object):

    def __init__(self, store):
        self.store = store

    def get_etag(self):
        return self.store.get_ctag()

    def members(self):
        ret = []
        for (name, etag) in self.store.iter_with_etag():
            resource = ObjectResource(
                self.store, name, etag, self._object_content_type)
            ret.append((name, resource))
        return ret

    def get_member(self, name):
        assert name != ''
        for (fname, fetag) in self.store.iter_with_etag():
            if name == fname:
                return ObjectResource(
                    self.store, name, fetag, self._object_content_type)
        else:
            raise KeyError(name)

    def delete_member(self, name, etag=None):
        self.store.delete_one(name, etag)

    def create_member(self, name, contents):
        self.store.import_one(name, b''.join(contents))


class Collection(StoreBasedCollection,caldav.Calendar):
    """A generic WebDAV collection."""

    _object_content_type = 'application/unknown'

    def __init__(self, store):
        self.store = store


class CalendarResource(StoreBasedCollection,caldav.Calendar):

    _object_content_type = 'text/calendar'

    def get_displayname(self):
        # TODO
        return os.path.basename(self.store.repo.path)

    def get_calendar_description(self):
        return self.store.get_description()

    def get_calendar_color(self):
        return self.store.get_color()

    def get_supported_calendar_components(self):
        return ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY"]

    def get_content_type(self):
        # TODO
        return 'text/calendar'

    def get_ctag(self):
        return self.store.get_ctag()


class AddressbookResource(StoreBasedCollection,carddav.Addressbook):

    _object_content_type = 'text/vcard'

    def get_content_type(self):
        # TODO
        raise KeyError

    def get_displayname(self):
        # TODO
        return os.path.basename(self.store.repo.path)

    def get_addressbook_description(self):
        return self.store.get_description()

    def get_supported_address_data_types(self):
        return [('text/vcard', '3.0')]


class CollectionSetResource(webdav.DAVCollection):
    """Resource for calendar sets."""

    def __init__(self, backend, relpath):
        self.backend = backend
        self.relpath = relpath

    def members(self):
        ret = []
        p = self.backend._map_to_file_path(self.relpath)
        for name in os.listdir(p):
            resource = self.get_member(name)
            ret.append((name, resource))
        return ret

    def get_member(self, name):
        assert name != ''
        relpath = posixpath.join(self.relpath, name)
        p = self.backend._map_to_file_path(relpath)
        if not os.path.isdir(p):
            raise KeyError(name)
        return self.backend.get_resource(relpath)


class Principal(CollectionSetResource):
    """Principal user resource."""

    resource_types = webdav.DAVCollection.resource_types + [webdav.PRINCIPAL_RESOURCE_TYPE]

    def get_principal_url(self):
        return self.path

    def get_calendar_home_set(self):
        return [CALENDAR_HOME]

    def get_addressbook_home_set(self):
        return [ADDRESSBOOK_HOME]

    def get_calendar_user_address_set(self):
        return USER_ADDRESS_SET


class DystrosBackend(webdav.DAVBackend):

    def __init__(self, path, current_user_principal):
        self.path = path
        self.current_user_principal = posixpath.normpath(current_user_principal)

    def _map_to_file_path(self, relpath):
        return os.path.join(self.path, relpath.lstrip('/'))

    def get_resource(self, relpath):
        relpath = posixpath.normpath(relpath)
        if relpath in WELLKNOWN_DAV_PATHS:
            return webdav.WellknownResource(self.current_user_principal)
        elif relpath == '/':
            return NonDAVResource()
        elif relpath == self.current_user_principal:
            return Principal(self, relpath)
        p = self._map_to_file_path(relpath)
        if p is None:
            return None
        if os.path.isdir(p):
            try:
                store = GitStore.open_from_path(p)
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


class DystrosApp(webdav.WebDAVApp):
    """A wsgi App that provides a Dystros web server.
    """

    def __init__(self, path, current_user_principal):
        super(DystrosApp, self).__init__(DystrosBackend(
            path, current_user_principal))
        self.register_properties([
            webdav.DAVResourceTypeProperty(),
            webdav.DAVCurrentUserPrincipalProperty(
                current_user_principal),
            webdav.DAVPrincipalURLProperty(),
            webdav.DAVDisplayNameProperty(),
            webdav.DAVGetETagProperty(),
            webdav.DAVGetContentTypeProperty(),
            caldav.CalendarHomeSetProperty(),
            caldav.CalendarUserAddressSetProperty(),
            carddav.AddressbookHomeSetProperty(),
            caldav.CalendarDescriptionProperty(),
            caldav.CalendarColorProperty(),
            caldav.SupportedCalendarComponentSetProperty(),
            carddav.AddressbookDescriptionProperty(),
            carddav.PrincipalAddressProperty(),
            caldav.GetCTagProperty(),
            carddav.SupportedAddressDataProperty(),
            ])
        self.register_reporters([
            caldav.CalendarMultiGetReporter(),
            caldav.CalendarQueryReporter(),
            carddav.AddressbookMultiGetReporter()])


if __name__ == '__main__':
    from dystros import utils
    import optparse
    import sys
    parser = optparse.OptionParser()
    parser.add_option("-l", "--listen_address", dest="listen_address",
                      default="localhost",
                      help="Binding IP address.")
    parser.add_option("-d", "--directory", dest="directory",
                      default=utils.DEFAULT_PATH,
                      help="Default path to serve from.")
    parser.add_option("-p", "--port", dest="port", type=int,
                      default=8000,
                      help="Port to listen on.")
    parser.add_option("--current-user-principal",
                      default="/user/",
                      help="Path to current user principal.")
    options, args = parser.parse_args(sys.argv)

    from wsgiref.simple_server import make_server
    app = DystrosApp(
        options.directory,
        current_user_principal=options.current_user_principal)
    server = make_server(options.listen_address, options.port, app)
    server.serve_forever()
