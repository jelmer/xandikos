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

"""Quota and Size properties.

See https://tools.ietf.org/html/rfc4331
"""

from xandikos import webdav

FEATURE: str = "quota"


class QuotaAvailableBytesProperty(webdav.Property):
    """quota-available-bytes."""

    name = "{DAV:}quota-available-bytes"
    resource_type = None
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_quota_available_bytes()


class QuotaUsedBytesProperty(webdav.Property):
    """quota-used-bytes."""

    name = "{DAV:}quota-used-bytes"
    resource_type = None
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_quota_used_bytes()
