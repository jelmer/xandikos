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

"""Simple CalDAV server."""

import defusedxml.ElementTree
from xml.etree import ElementTree as ET

from dystros.webdav import (
    DavResource,
    WebDAVApp,
    )


CALENDAR_HOME_SET = '/user/calendars/'
CURRENT_USER_PRINCIPAL = '/user/'
DEFAULT_ENCODING = 'utf-8'


WELLKNOWN_DAV_PATHS = set(["/.well-known/caldav", "/.well-known/carddav"])


class WellknownResource(DavResource):
    """Resource for well known URLs."""

    def __init__(self, server_root):
        self.server_root = server_root

    def propget(self, name):
        """Get property with specified name.

        :param name: A property name.
        """
        return super(WellknownResource, self).propget(name)

    def get_body(self):
        return [self.server_root.encode(DEFAULT_ENCODING)]

    def members(self):
        return []


class NonDavResource(DavResource):
    """A non-DAV resource that is DAV enabled."""

    def propget(self, name):
        """Get property with specified name.

        :param name: A property name.
        """
        if name == '{DAV:}resourcetype':
            return ET.Element('{DAV:}resourcetype')
        else:
            return super(NonDavResource, self).propget(name)

    def members(self):
        return []


class UserPrincipalResource(DavResource):
    """Resource for a user principal."""

    def propget(self, name):
        """Get property with specified name.

        :param name: A property name.
        """
        if name == '{urn:ietf:params:xml:ns:caldav}calendar-home-set':
            ret = ET.Element('{urn:ietf:params:xml:ns:caldav}calendar-home-set')
            ET.SubElement(ret, '{DAV:}href').text = CALENDAR_HOME_SET
            return ret
        else:
            return super(UserPrincipalResource, self).propget(name)


class Collection(DavResource):
    """Resource for calendar sets."""

    def propget(self, name):
        """Get property with specified name.

        :param name: A property name.
        """
        if name == '{DAV:}resourcetype':
            ret = ET.Element('{DAV:}resourcetype')
            ET.SubElement(ret, '{DAV:}collection')
            return ret
        return super(Collection, self).propget(name)

    def members(self):
        raise NotImplementedError(self.members)


class CalendarSetResource(DavResource):
    """Resource for calendar sets."""

    def propget(self, name):
        """Get property with specified name.

        :param name: A property name.
        """
        if name == '{DAV:}resourcetype':
            ret = ET.Element('{DAV:}resourcetype')
            ET.SubElement(ret, '{DAV:}collection')
            return ret
        return super(CalendarSetResource, self).propget(name)

    def members(self):
        return [('foo', Collection())]


def lookup_resource(p):
    if p in WELLKNOWN_DAV_PATHS:
        r = WellknownResource("/")
    elif p == "/":
        return NonDavResource()
    elif p == CURRENT_USER_PRINCIPAL:
        return UserPrincipalResource()
    elif p == CALENDAR_HOME_SET:
        return CalendarSetResource()
    else:
        return None


if __name__ == '__main__':
    import optparse
    import sys
    parser = optparse.OptionParser()
    parser.add_option("-l", "--listen_address", dest="listen_address",
                      default="localhost",
                      help="Binding IP address.")
    parser.add_option("-p", "--port", dest="port", type=int,
                      default=8000,
                      help="Port to listen on.")
    options, args = parser.parse_args(sys.argv)

    from wsgiref.simple_server import make_server
    app = WebDAVApp(lookup_resource)
    server = make_server(options.listen_address, options.port, app)
    server.serve_forever()
