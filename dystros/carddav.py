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

"""CardDAV support.

https://tools.ietf.org/html/rfc6352
"""
import defusedxml.ElementTree
from xml.etree import ElementTree as ET

from dystros import davcommon, webdav

WELLKNOWN_CARDDAV_PATH = "/.well-known/carddav"

NAMESPACE = 'urn:ietf:params:xml:ns:carddav'
ADDRESSBOOK_RESOURCE_TYPE = '{%s}addressbook' % NAMESPACE


class AddressbookHomeSetProperty(webdav.DAVProperty):
    """addressbook-home-set property

    See https://tools.ietf.org/html/rfc6352, section 7.1.1
    """

    name = '{%s}addressbook-home-set' % NAMESPACE
    resource_type = '{DAV:}principal'
    in_allprops = False

    def populate(self, resource, el):
        for href in resource.get_addressbook_home_set():
            ET.SubElement(el, '{DAV:}href').text = href


class AddressDataProperty(webdav.DAVProperty):
    """address-data property

    See https://tools.ietf.org/html/rfc6352, section 10.4

    Note that this is not technically a DAV property, and
    it is thus not registered in the regular webdav server.
    """

    name = '{%s}address-data' % NAMESPACE

    def populate(self, resource, el):
        # TODO(jelmer): Support subproperties
        # TODO(jelmer): Don't hardcode encoding
        el.text = b''.join(resource.get_body()).decode('utf-8')


class AddressbookDescriptionProperty(webdav.DAVProperty):
    """Provides calendar-description property.

    https://tools.ietf.org/html/rfc6352, section 6.2.1
    """

    name = '{%s}addressbook-description' % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE

    def populate(self, resource, el):
        el.text = resource.get_addressbook_description()

    # TODO(jelmer): allow modification of this property
    # protected = True


class AddressbookMultiGetReporter(davcommon.MultiGetReporter):

    name = '{%s}addressbook-multiget' % NAMESPACE

    data_property_kls = AddressDataProperty


class Addressbook(webdav.DAVCollection):

    resource_types = (
        webdav.DAVCollection.resource_types + [ADDRESSBOOK_RESOURCE_TYPE])

    def get_addressbook_description(self):
        raise NotImplementedError(self.get_addressbook_description)


class PrincipalExtensions:
    """Extensions to webdav.Principal."""

    def get_addressbook_home_set(self):
        """Return set of addressbook home URLs.

        :return: set of URLs
        """
        raise NotImplementedError(self.get_addressbook_home_set)

    def get_principal_address(self):
        """Return URL to principal address vCard."""
        raise NotImplementedError(self.get_principal_address)


class PrincipalAddressProperty(webdav.DAVProperty):
    """Provides the principal-address property.

    https://tools.ietf.org/html/rfc6352, section 7.1.2
    """

    name = '{%s}principal-address' % NAMESPACE
    resource_type = '{DAV:}principal'
    in_allprops = False

    def populate(self, resource, el):
        ET.SubElement(el, '{DAV:}href').text = resource.get_principal_address()
