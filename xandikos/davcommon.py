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

    def get_value_ext(self, href, resource, el, environ, requested):
        """Get the value of a data property.

        :param href: Resource href
        :param resource: Resource to get value for
        :param el: Element to fill in
        :param environ: WSGI environ dict
        :param requested: Requested property (including subelements)
        """
        raise NotImplementedError(self.get_value_ext)


def get_properties_with_data(data_property, href, resource, properties,
                             environ, requested):
    properties = dict(properties)
    properties[data_property.name] = data_property
    return webdav.get_properties(
        href, resource, properties, environ, requested)


class MultiGetReporter(webdav.Reporter):
    """Abstract base class for multi-get reporters."""

    name = None

    # A SubbedProperty subclass
    data_property = None

    @webdav.multistatus
    def report(self, environ, body, resources_by_hrefs, properties, base_href,
               resource, depth):
        # TODO(jelmer): Verify that depth == "0"
        # TODO(jelmer): Verify that resource is an the right resource type
        requested = None
        hrefs = []
        for el in body:
            if el.tag in ('{DAV:}prop', '{DAV:}allprop', '{DAV:}propname'):
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
                    self.data_property, href, resource, properties, environ,
                    requested)
                yield webdav.Status(href, '200 OK', propstat=list(propstat))


# see https://tools.ietf.org/html/rfc4790
