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

"""CardDAV support.

https://tools.ietf.org/html/rfc6352
"""

import itertools

from . import collation as _mod_collation
from . import davcommon, webdav

ET = webdav.ET

WELLKNOWN_CARDDAV_PATH = "/.well-known/carddav"

NAMESPACE = "urn:ietf:params:xml:ns:carddav"
ADDRESSBOOK_RESOURCE_TYPE = "{%s}addressbook" % NAMESPACE

# Feature to advertise presence of CardDAV support
FEATURE = "addressbook"


class AddressbookHomeSetProperty(webdav.Property):
    """addressbook-home-set property.

    See https://tools.ietf.org/html/rfc6352, section 7.1.1
    """

    name = "{%s}addressbook-home-set" % NAMESPACE
    resource_type = "{DAV:}principal"
    in_allprops = False
    live = True

    async def get_value(self, base_href, resource, el, environ):
        for href in resource.get_addressbook_home_set():
            href = webdav.ensure_trailing_slash(href)
            el.append(webdav.create_href(href, base_href))


class AddressDataProperty(davcommon.SubbedProperty):
    """address-data property.

    See https://tools.ietf.org/html/rfc6352, section 10.4

    Note that this is not technically a DAV property, and
    it is thus not registered in the regular webdav server.
    """

    name = "{%s}address-data" % NAMESPACE

    def supported_on(self, resource):
        try:
            return resource.get_content_type() == "text/vcard"
        except KeyError:
            # Resource doesn't have a content type
            return False

    async def get_value_ext(self, href, resource, el, environ, requested):
        # TODO(jelmer): Support subproperties
        # UTF-8 encoding is required by RFC 6350 (vCard format)
        el.text = b"".join(await resource.get_body()).decode("utf-8")


class AddressbookDescriptionProperty(webdav.Property):
    """Provides calendar-description property.

    https://tools.ietf.org/html/rfc6352, section 6.2.1
    """

    name = "{%s}addressbook-description" % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_addressbook_description()

    async def set_value(self, href, resource, el):
        resource.set_addressbook_description(el.text)


class AddressbookMultiGetReporter(davcommon.MultiGetReporter):
    name = "{%s}addressbook-multiget" % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE
    data_property = AddressDataProperty()

    async def report(
        self,
        environ,
        body,
        resources_by_hrefs,
        properties,
        base_href,
        resource,
        depth,
        strict,
    ):
        # RFC 6352 Section 8.7 (CardDAV addressbook-multiget) specifies:
        #   "The request MUST include a Depth: 0 header on the request."
        #
        # This is a client requirement, and the RFC doesn't explicitly mandate
        # that servers MUST reject requests with other Depth values. However,
        # in strict mode, we enforce this requirement to ensure full RFC
        # compliance and catch misbehaving clients.
        #
        # In non-strict mode, we accept any Depth value for compatibility with
        # existing clients that may send non-zero Depth headers.
        if strict and depth != "0":
            raise webdav.BadRequestError(
                f"{self.name} requires Depth: 0 (RFC 6352 Section 8.7), "
                f"got Depth: {depth}"
            )
        return await super().report(
            environ,
            body,
            resources_by_hrefs,
            properties,
            base_href,
            resource,
            depth,
            strict,
        )


class Addressbook(webdav.Collection):
    resource_types = webdav.Collection.resource_types + [ADDRESSBOOK_RESOURCE_TYPE]

    def get_addressbook_description(self) -> str:
        raise NotImplementedError(self.get_addressbook_description)

    def set_addressbook_description(self, description: str) -> None:
        raise NotImplementedError(self.set_addressbook_description)

    def get_addressbook_color(self) -> str:
        raise NotImplementedError(self.get_addressbook_color)

    def set_addressbook_color(self, color: str) -> None:
        raise NotImplementedError(self.set_addressbook_color)

    def get_supported_address_data_types(self):
        """Get list of supported data types.

        Returns: List of tuples with content type and version
        """
        raise NotImplementedError(self.get_supported_address_data_types)

    def get_max_resource_size(self) -> int:
        """Get maximum object size this address book will store (in bytes).

        Absence indicates no maximum.
        """
        raise NotImplementedError(self.get_max_resource_size)

    def get_max_image_size(self) -> int:
        """Get maximum image size this address book will store (in bytes).

        Absence indicates no maximum.
        """
        raise NotImplementedError(self.get_max_image_size)


class PrincipalExtensions:
    """Extensions to webdav.Principal."""

    def get_addressbook_home_set(self) -> set[str]:
        """Return set of addressbook home URLs.

        Returns: set of URLs
        """
        raise NotImplementedError(self.get_addressbook_home_set)

    def get_principal_address(self) -> str:
        """Return URL to principal address vCard."""
        raise NotImplementedError(self.get_principal_address)


class PrincipalAddressProperty(webdav.Property):
    """Provides the principal-address property.

    https://tools.ietf.org/html/rfc6352, section 7.1.2
    """

    name = "{%s}principal-address" % NAMESPACE
    resource_type = "{DAV:}principal"
    in_allprops = False

    async def get_value(self, href, resource, el, environ):
        el.append(webdav.create_href(resource.get_principal_address(), href))


class SupportedAddressDataProperty(webdav.Property):
    """Provides the supported-address-data property.

    https://tools.ietf.org/html/rfc6352, section 6.2.2
    """

    name = "{%s}supported-address-data" % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        for (
            content_type,
            version,
        ) in resource.get_supported_address_data_types():
            subel = ET.SubElement(el, "{%s}content-type" % NAMESPACE)
            subel.set("content-type", content_type)
            subel.set("version", version)


class MaxResourceSizeProperty(webdav.Property):
    """Provides the max-resource-size property.

    See https://tools.ietf.org/html/rfc6352, section 6.2.3.
    """

    name = "{%s}max-resource-size" % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_resource_size())


class MaxImageSizeProperty(webdav.Property):
    """Provides the max-image-size property.

    This seems to be a carddav extension used by iOS and caldavzap.
    """

    name = "{%s}max-image-size" % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_image_size())


async def addressbook_from_resource(resource):
    try:
        if resource.get_content_type() != "text/vcard":
            return None
    except KeyError:
        return None
    file = await resource.get_file()
    return file.addressbook.contents


def apply_text_match(el: ET.Element, value: str) -> bool:
    collation = el.get("collation", "i;ascii-casemap")
    negate_condition = el.get("negate-condition", "no")
    match_type = el.get("match-type", "contains")
    matches = _mod_collation.collations[collation](value, el.text or "", match_type)

    if negate_condition == "yes":
        return not matches
    else:
        return matches


def apply_param_filter(el, prop):
    name = el.get("name")
    if len(el) == 1 and el[0].tag == "{urn:ietf:params:xml:ns:carddav}is-not-defined":
        return name not in prop.params

    try:
        value = prop.params[name]
    except KeyError:
        return False

    for subel in el:
        if subel.tag == "{urn:ietf:params:xml:ns:carddav}text-match":
            if not apply_text_match(subel, value):
                return False
        else:
            raise AssertionError("unknown tag %r in param-filter", subel.tag)
    return True


def apply_prop_filter(el, ab):
    name = el.get("name").lower()
    # From https://tools.ietf.org/html/rfc6352
    # A CARDDAV:prop-filter is said to match if:

    # The CARDDAV:prop-filter XML element contains a CARDDAV:is-not-defined XML
    # element and no property of the type specified by the "name" attribute
    # exists in the enclosing calendar component;
    if len(el) == 1 and el[0].tag == "{urn:ietf:params:xml:ns:carddav}is-not-defined":
        return name not in ab

    try:
        prop = ab[name]
    except KeyError:
        return False

    for prop_el in prop:
        matched = True
        for subel in el:
            if subel.tag == "{urn:ietf:params:xml:ns:carddav}text-match":
                if not apply_text_match(subel, str(prop_el)):
                    matched = False
                    break
            elif subel.tag == "{urn:ietf:params:xml:ns:carddav}param-filter":
                if not apply_param_filter(subel, prop_el):
                    matched = False
                    break
        if matched:
            return True
    return False


def parse_filter(filter_el, cls):
    """Parse a CardDAV filter element and build a filter object."""
    if filter_el is None:
        return cls

    test_name = filter_el.get("test", "anyof")
    cls.test = {"allof": all, "anyof": any}[test_name]

    for prop_el in filter_el:
        if prop_el.tag == "{urn:ietf:params:xml:ns:carddav}prop-filter":
            parse_prop_filter(prop_el, cls)
        else:
            raise AssertionError(f"unknown filter tag {prop_el.tag!r}")

    return cls


def parse_prop_filter(prop_el, filter_obj):
    """Parse a prop-filter element and add it to the filter."""
    name = prop_el.get("name")
    text_match = None
    param_filters = []
    is_not_defined = False

    for subel in prop_el:
        if subel.tag == "{urn:ietf:params:xml:ns:carddav}is-not-defined":
            is_not_defined = True
        elif subel.tag == "{urn:ietf:params:xml:ns:carddav}text-match":
            text_match = {
                "text": subel.text or "",
                "collation": subel.get("collation", "i;unicode-casemap"),
                "negate_condition": subel.get("negate-condition", "no") == "yes",
                "match_type": subel.get("match-type", "contains"),
            }
        elif subel.tag == "{urn:ietf:params:xml:ns:carddav}param-filter":
            # param-filter is handled by apply_param_filter() during query execution
            pass

    filter_obj.add_prop_filter(name, text_match, param_filters, is_not_defined)


async def apply_filter(el, resource):
    """Compile a filter element into a Python function."""
    if el is None or not list(el):
        # Empty filter, let's not bother parsing
        return lambda x: True
    ab = await addressbook_from_resource(resource)
    if ab is None:
        return False
    test_name = el.get("test", "anyof")
    test = {"allof": all, "anyof": any}[test_name]
    return test(apply_prop_filter(subel, ab) for subel in el)


class AddressbookQueryReporter(webdav.Reporter):
    name = "{%s}addressbook-query" % NAMESPACE
    resource_type = ADDRESSBOOK_RESOURCE_TYPE
    data_property = AddressDataProperty()

    @webdav.multistatus
    async def report(
        self,
        environ,
        body,
        resources_by_hrefs,
        properties,
        base_href,
        base_resource,
        depth,
        strict,
    ):
        requested = None
        filter_el = None
        limit = None
        for el in body:
            if el.tag in ("{DAV:}prop", "{DAV:}allprop", "{DAV:}propname"):
                requested = el
            elif el.tag == ("{%s}filter" % NAMESPACE):
                filter_el = el
            elif el.tag == ("{%s}limit" % NAMESPACE):
                limit = el
            else:
                webdav.nonfatal_bad_request(
                    f"Unknown tag {el.tag} in report {self.name}", strict
                )
        if requested is None:
            # The CardDAV RFC says that behaviour mimics that of PROPFIND,
            # and the WebDAV RFC says that no body implies {DAV}allprop
            # This isn't exactly an empty body, but close enough.
            requested = ET.Element("{DAV:}allprop")
        if limit is not None:
            try:
                [nresults_el] = list(limit)
            except ValueError:
                webdav.nonfatal_bad_request(
                    "Invalid number of subelements in limit", strict
                )
                nresults = None
            else:
                try:
                    nresults = int(nresults_el.text)
                except ValueError:
                    webdav.nonfatal_bad_request("nresults not a number", strict)
                    nresults = None
        else:
            nresults = None

        def filter_fn(cls):
            return parse_filter(filter_el, cls())

        def members(collection):
            return itertools.chain(
                collection.addressbook_query(filter_fn),
                collection.subcollections(),
            )

        i = 0
        async for href, resource in webdav.traverse_resource(
            base_resource, base_href, depth, members=members
        ):
            # Ideally traverse_resource would only return the right things.
            if getattr(resource, "content_type", None) == "text/vcard":
                if nresults is not None and i >= nresults:
                    break
                propstat = davcommon.get_properties_with_data(
                    self.data_property,
                    href,
                    resource,
                    properties,
                    environ,
                    requested,
                )
                yield webdav.Status(
                    href, "200 OK", propstat=[s async for s in propstat]
                )
                i += 1
