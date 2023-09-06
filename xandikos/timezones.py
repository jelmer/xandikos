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

"""Timezone handling.

See http://www.webdav.org/specs/rfc7809.html
"""

from xandikos import webdav


class TimezoneServiceSetProperty(webdav.Property):
    """timezone-service-set property.

    See http://www.webdav.org/specs/rfc7809.html, section 5.1
    """

    name = "{DAV:}timezone-service-set"
    # Should be set on CalDAV calendar home collection resources,
    # but Xandikos doesn't have a separate resource type for those.
    resource_type = webdav.COLLECTION_RESOURCE_TYPE
    in_allprops = False
    live = True

    def __init__(self, timezone_services) -> None:
        super().__init__()
        self._timezone_services = timezone_services

    async def get_value(self, base_href, resource, el, environ):
        for timezone_service_href in self._timezone_services:
            el.append(webdav.create_href(timezone_service_href, base_href))
