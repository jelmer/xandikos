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

"""Access control.

See http://www.webdav.org/specs/rfc3744.html
"""

from xandikos import webdav

ET = webdav.ET

# Feature to advertise access control support.
FEATURE = "access-control"


class CurrentUserPrivilegeSetProperty(webdav.Property):
    """current-user-privilege-set property.

    See http://www.webdav.org/specs/rfc3744.html, section 3.7
    """

    name = "{DAV:}current-user-privilege-set"
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        privilege = ET.SubElement(el, "{DAV:}privilege")
        # TODO(jelmer): Use something other than all
        ET.SubElement(privilege, "{DAV:}all")


class OwnerProperty(webdav.Property):
    """owner property.

    See http://www.webdav.org/specs/rfc3744.html, section 5.1
    """

    name = "{DAV:}owner"
    in_allprops = False
    live = True

    async def get_value(self, base_href, resource, el, environ):
        owner_href = resource.get_owner()
        if owner_href is not None:
            el.append(webdav.create_href(owner_href, base_href=base_href))


class GroupMembershipProperty(webdav.Property):
    """Group membership.

    See https://www.ietf.org/rfc/rfc3744.txt, section 4.4
    """

    name = "{DAV:}group-membership"
    in_allprops = False
    live = True
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE

    async def get_value(self, base_href, resource, el, environ):
        for href in resource.get_group_membership():
            el.append(webdav.create_href(href, base_href=href))
