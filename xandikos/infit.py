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

"""Inf-It properties."""

from xandikos import carddav, webdav


class SettingsProperty(webdav.Property):
    """settings property.

    JSON settings.
    """

    name = "{http://inf-it.com/ns/dav/}settings"
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    live = False

    async def get_value(self, href: str, resource, el, environ):
        el.text = resource.get_infit_settings()

    async def set_value(self, href: str, resource, el):
        resource.set_infit_settings(el.text)


class AddressbookColorProperty(webdav.Property):
    """Provides the addressbook-color property.

    Contains a RRGGBB code, similar to calendar-color.
    """

    name = "{http://inf-it.com/ns/ab/}addressbook-color"
    resource_type = carddav.ADDRESSBOOK_RESOURCE_TYPE
    in_allprops = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_addressbook_color()

    async def set_value(self, href, resource, el):
        resource.set_addressbook_color(el.text)


class HeaderValueProperty(webdav.Property):
    """Provides the header-value property.

    This behaves similar to the hrefLabel setting in caldavzap/carddavmate.
    """

    name = "{http://inf-it.com/ns/dav/}headervalue"
    resource_type = webdav.COLLECTION_RESOURCE_TYPE
    in_allprops = False
    live = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_headervalue()

    async def set_value(self, href, resource, el):
        # TODO
        raise NotImplementedError
