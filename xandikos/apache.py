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

"""Apache.org mod_dav custom properties.

See http://www.webdav.org/mod_dav/
"""

from xandikos import webdav


class ExecutableProperty(webdav.Property):
    """executable property.

    Equivalent of the 'x' bit on POSIX.
    """

    name = "{http://apache.org/dav/props/}executable"
    resource_type = None
    live = False

    async def get_value(self, href, resource, el, environ):
        el.text = "T" if resource.get_is_executable() else "F"

    async def set_value(self, href, resource, el):
        if el.text == "T":
            resource.set_is_executable(True)
        elif el.text == "F":
            resource.set_is_executable(False)
        else:
            raise ValueError(f"invalid executable setting {el.text!r}")
