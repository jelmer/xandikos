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

"""Inf-It properties.
"""
import defusedxml.ElementTree
from xml.etree import ElementTree as ET

from xandikos import webdav, carddav


class SettingsProperty(webdav.Property):
    """settings propety.

    JSON settings.
    """

    name = '{http://inf-it.com/ns/dav/}settings'
    protected = False
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    live = False

    def get_value(self, resource, el):
        el.text = resource.get_infit_settings()

    def set_value(self, resource, el):
        resource.set_infit_settings(el.text)


class AddressbookColorProperty(webdav.Property):
    """Provides the addressbook-color property.

    Contains a RRGGBB code, similar to calendar-color.
    """

    name = '{http://inf-it.com/ns/ab/}addressbook-color'
    resource_type = carddav.ADDRESSBOOK_RESOURCE_TYPE
    in_allprops = False
    protected = False

    def get_value(self, resource, el):
        el.text = resource.get_addressbook_color()


class HeaderValueProperty(webdav.Property):
    """Provides the header-value property.

    This behaves similar to the hrefLabel setting in caldavzap/carddavmate.
    """


    name = '{http://inf-it.com/ns/dav/}headervalue'
    resource_type = webdav.COLLECTION_RESOURCE_TYPE
    in_allprops = False
    protected = False
    live = False

    def get_value(self, resource, el):
        el.text = resource.get_headervalue()
