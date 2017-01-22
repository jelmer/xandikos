l Dystros
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

"""Common functions for DAV implementations."""

from dystros import webdav

class MultiGetReporter(webdav.DAVReporter):
    """Abstract base class for multi-get reporters."""

    name = None

    data_property_kls = None

    def report(self, body, resource_by_href, properties, base_href, resource, depth):
        # TODO(jelmer): Verify that depth == "0"
        # TODO(jelmer): Verify that resource is an addressbook
        requested = None
        hrefs = []
        for el in body:
            if el.tag == '{DAV:}prop':
                requested = el
            elif el.tag == '{DAV:}href':
                hrefs.append(el.text)
            else:
                raise NotImplementedError(tag.name)
        properties = dict(properties)
        properties[self.data_property_kls.name] = self.data_property_kls()
        for href in hrefs:
            try:
                resource = resource_by_href(href)
            except KeyError:
                yield webdav.DAVStatus(href, '404 Not Found', propstat=[])
            else:
                propstat = webdav.resolve_properties(
                    resource, properties, requested)
                yield webdav.DAVStatus(href, '200 OK', propstat=list(propstat))
