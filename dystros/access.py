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

"""Access control.

See http://www.webdav.org/specs/rfc3744.html
"""

from defusedxml.ElementTree import fromstring as xmlparse
from xml.etree import ElementTree as ET

from dystros import webdav


class CurrentUserPrivilegeSetProperty(webdav.DAVProperty):
    """current-user-privilege-set property

    See http://www.webdav.org/specs/rfc3744.html, section 3.7
    """

    name = '{DAV:}current-user-privilege-set'
    in_allprops = False
    protected = True

    def get_value(self, resource, el):
       privilege = ET.SubElement(el, '{DAV:}privilege')
       # TODO(jelmer): Use something other than all
       priv_all = ET.SubElement(privilege, '{DAV:}all')
