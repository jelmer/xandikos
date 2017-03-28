# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooij <jelmer@jelmer.uk>
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

    def get_value(self, href, resource, el, requested):
        """Get the value of a data property.

        :param href: Resource href
        :param resource: Resource to get value for
        :param el: Element to fill in
        :param requested: Requested property (including subelements)
        """
        raise NotImplementedError(self.get_value)


def get_properties_with_data(data_property, href, resource, properties,
                             requested):
    for propreq in list(requested):
        if propreq.tag == data_property.name:
            ret = ET.Element(propreq.tag)
            if data_property.supported_on(resource):
                data_property.get_value(href, resource, ret, propreq)
                statuscode = '200 OK'
            else:
                statuscode = '404 Not Found'
            yield webdav.PropStatus(statuscode, None, ret)
        else:
            yield webdav.get_property(href, resource, properties, propreq.tag)


class MultiGetReporter(webdav.Reporter):
    """Abstract base class for multi-get reporters."""

    name = None

    # A SubbedProperty subclass
    data_property = None

    @webdav.multistatus
    def report(self, environ, body, resources_by_hrefs, properties, base_href,
               resource, depth):
        # TODO(jelmer): Verify that depth == "0"
        # TODO(jelmer): Verify that resource is an addressbook
        requested = None
        hrefs = []
        for el in body:
            if el.tag == '{DAV:}prop':
                requested = el
            elif el.tag == '{DAV:}href':
                hrefs.append(webdav.read_href_element(el))
            else:
                raise webdav.BadRequestError(
                    'Unknown tag %s in report %s' % (el.tag, self.name))
        for (href, resource) in resources_by_hrefs(hrefs):
            if resource is None:
                yield webdav.Status(href, '404 Not Found', propstat=[])
            else:
                propstat = get_properties_with_data(
                    self.data_property, href, resource, properties, requested)
                yield webdav.Status(href, '200 OK', propstat=list(propstat))


# see https://tools.ietf.org/html/rfc4790

collations = {
    'i;ascii-casemap': lambda a, b: (a.decode('ascii').upper() ==
                                     b.decode('ascii').upper()),
    'i;octet': lambda a, b: a == b,
}
