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

"""Access control.

See http://www.webdav.org/specs/rfc3744.html
"""

from defusedxml.ElementTree import fromstring as xmlparse
from xml.etree import ElementTree as ET

from xandikos import webdav


class CurrentUserPrivilegeSetProperty(webdav.Property):
    """current-user-privilege-set property

    See http://www.webdav.org/specs/rfc3744.html, section 3.7
    """

    name = '{DAV:}current-user-privilege-set'
    in_allprops = False
    protected = True
    live = True

    def get_value(self, resource, el):
       privilege = ET.SubElement(el, '{DAV:}privilege')
       # TODO(jelmer): Use something other than all
       priv_all = ET.SubElement(privilege, '{DAV:}all')


class OwnerProperty(webdav.Property):
    """owner property.

    See http://www.webdav.org/specs/rfc3744.html, section 5.1
    """

    name = '{DAV:}owner'
    in_allprops = False
    live = True

    def get_value(self, resource, el):
       owner_href = resource.get_owner()
       if owner_href is not None:
           ET.SubElement(el, '{DAV:}href').href = owner_href

