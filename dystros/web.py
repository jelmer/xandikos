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

from dystros import caldav, carddav, utils, webdav
from dystros.store import (
    GitStore,
    NotStoreError,
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_OTHER,
    )

WELLKNOWN_DAV_PATHS = set([caldav.WELLKNOWN_CALDAV_PATH, carddav.WELLKNOWN_CARDDAV_PATH])

# TODO(jelmer): Make these configurable/dynamic
CALENDAR_HOME_SET = ['/user/calendars/']
ADDRESSBOOK_HOME_SET = ['/user/contacts/']
CURRENT_USER_PRINCIPAL = '/user/'
PRINCIPAL_URL = 'http://localhost/user/'
USER_ADDRESS_SET = 'mailto:jelmer@jelmer.uk'


class ObjectResource(webdav.DAVResource):
    """Object resource."""

    def __init__(self, store, name, etag, content_type):
        self.store = store
        self.name = name
        self.etag = etag
        self.content_type = content_type

    def get_body(self):
        return self.store.get_raw(self.name, self.etag)

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
        return "A calendar resource"

    def get_calendar_description(self):
        # TODO
        return "A calendar"

    def get_calendar_color(self):
        # TODO
        return "#112233"

    def get_supported_calendar_components(self):
        return ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY"]

    def get_content_type(self):
        # TODO
        return 'text/calendar'


class AddressbookResource(StoreBasedCollection,carddav.Addressbook):

    _object_content_type = 'text/vcard'

    def get_content_type(self):
        # TODO
        raise KeyError

    def get_displayname(self):
        # TODO
        return "An addressbook resource"

    def get_addressbook_description(self):
        # TODO
        raise KeyError


def open_from_path(p):
    """Open a WebDAV collection from a file path.

    :param p: Absolute filesystem path
    :return: A Resource object, or None
    """
    if os.path.isdir(p):
        if p.endswith('/user/'):
            return Principal(p)
        try:
            store = GitStore.open_from_path(p)
        except NotStoreError:
            return CollectionSetResource(p)
        else:
            return {STORE_TYPE_CALENDAR: CalendarResource,
                    STORE_TYPE_ADDRESSBOOK: AddressbookResource,
                    STORE_TYPE_OTHER: Collection}[store.get_type()](store)
    else:
        (basepath, name) = os.path.split(p)
        store = open_from_path(basepath)
        try:
            return store.get_member(name)
        except KeyError:
            return None


class CollectionSetResource(webdav.DAVCollection):
    """Resource for calendar sets."""

    def __init__(self, path):
        self.path = path

    def members(self):
        ret = []
        for name in os.listdir(self.path):
            resource = self.get_member(name)
            ret.append((name, resource))
        return ret

    def get_member(self, name):
        p = os.path.join(self.path, name)
        resource = open_from_path(p)
        if resource is None:
            raise KeyError(name)
        return resource


class Principal(CollectionSetResource):
    """Principal user resource."""

    resource_types = webdav.DAVCollection.resource_types + [webdav.PRINCIPAL_RESOURCE_TYPE]

    def get_principal_url(self):
        return PRINCIPAL_URL

    def get_calendar_home_set(self):
        return CALENDAR_HOME_SET

    def get_addressbook_home_set(self):
        return ADDRESSBOOK_HOME_SET

    def get_calendar_user_address_set(self):
        return USER_ADDRESS_SET


class DystrosBackend(webdav.DAVBackend):

    def __init__(self, path):
        self.path = path

    def get_resource(self, relpath):
        if relpath in WELLKNOWN_DAV_PATHS:
            return webdav.WellknownResource('/')
        elif relpath == '/':
            return webdav.NonDAVResource()
        else:
            p = os.path.join(self.path, relpath.lstrip('/'))
            try:
                return open_from_path(p)
            except NotStoreError:
                return None


class DystrosApp(webdav.WebDAVApp):
    """A wsgi App that provides a Dystros web server.
    """

    def __init__(self, path):
        super(DystrosApp, self).__init__(DystrosBackend(path))
        self.register_properties([
            webdav.DAVResourceTypeProperty(),
            webdav.DAVCurrentUserPrincipalProperty(CURRENT_USER_PRINCIPAL),
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
            ])
        self.register_reporters([
            caldav.CalendarMultiGetReporter(),
            carddav.AddressbookMultiGetReporter()])


if __name__ == '__main__':
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
    options, args = parser.parse_args(sys.argv)

    from wsgiref.simple_server import make_server
    app = DystrosApp(options.directory)
    server = make_server(options.listen_address, options.port, app)
    server.serve_forever()
