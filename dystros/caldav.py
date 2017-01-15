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
    DAVBackend,
    DAVProperty,
    DAVResource,
    WebDAVApp,
    )


WELLKNOWN_CALDAV_PATH = "/.well-known/caldav"


class CalDAVHomeSetProperty(DAVProperty):
    """calendar-home-set property

    See https://www.ietf.org/rfc/rfc4791.txt, section 6.2.1.
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-home-set'
    in_allprops = False

    def propget(self, resource, name):
        """Get property with specified name.

        :param name: A property name.
        """
        if name == self.name:
            ret = ET.Element(self.name)
            ET.SubElement(ret, '{DAV:}href').text = CALENDAR_HOME_SET
            return ret
        raise KeyError


class CalendarSetResource(DAVResource):
    """Resource for calendar sets."""

    def members(self):
        return [('foo', Collection())]
