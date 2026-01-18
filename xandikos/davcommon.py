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

"""Common functions for DAV implementations."""

from xandikos import webdav

ET = webdav.ET


class SubbedProperty(webdav.Property):
    """Property with sub-components that can be queried."""

    async def get_value_ext(self, href, resource, el, environ, requested):
        """Get the value of a data property.

        Args:
          href: Resource href
          resource: Resource to get value for
          el: Element to fill in
          environ: WSGI environ dict
          requested: Requested property (including subelements)
        """
        raise NotImplementedError(self.get_value_ext)


async def get_properties_with_data(
    data_property, href, resource, properties, environ, requested
):
    properties = dict(properties)
    properties[data_property.name] = data_property
    async for ps in webdav.get_properties(
        href, resource, properties, environ, requested
    ):
        yield ps


class MultiGetReporter(webdav.Reporter):
    """Abstract base class for multi-get reporters."""

    name: str

    # A SubbedProperty subclass
    data_property: SubbedProperty

    @webdav.multistatus
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
        # Note: Resource type validation is performed by the REPORT handler
        # via supported_on() before this method is called
        # Note: Depth header validation is handled by subclasses as needed
        requested = None
        hrefs = []
        for el in body:
            if el.tag in ("{DAV:}prop", "{DAV:}allprop", "{DAV:}propname"):
                requested = el
            elif el.tag == "{DAV:}href":
                hrefs.append(webdav.read_href_element(el))
            else:
                webdav.nonfatal_bad_request(
                    f"Unknown tag {el.tag} in report {self.name}", strict
                )
        if requested is None:
            # The CalDAV RFC says that behaviour mimics that of PROPFIND,
            # and the WebDAV RFC says that no body implies {DAV}allprop
            # This isn't exactly an empty body, but close enough.
            requested = ET.Element("{DAV:}allprop")
        for href, resource in resources_by_hrefs(hrefs):
            if resource is None:
                yield webdav.Status(href, "404 Not Found", propstat=[])
            else:
                propstat = get_properties_with_data(
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


# see https://tools.ietf.org/html/rfc4790
