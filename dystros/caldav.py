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

"""Simple CalDAV server.

https://tools.ietf.org/html/rfc4791
"""

import defusedxml.ElementTree
from xml.etree import ElementTree as ET

from dystros import davcommon
from dystros.webdav import (
    DAVBackend,
    DAVCollection,
    DAVProperty,
    DAVReporter,
    DAVResource,
    DAVStatus,
    WebDAVApp,
    get_properties,
    traverse_resource,
    )


WELLKNOWN_CALDAV_PATH = "/.well-known/caldav"

# https://tools.ietf.org/html/rfc4791, section 4.2
CALENDAR_RESOURCE_TYPE = '{urn:ietf:params:xml:ns:caldav}calendar'

NAMESPACE = 'urn:ietf:params:xml:ns:caldav'


class Calendar(DAVCollection):

    resource_types = DAVCollection.resource_types + [CALENDAR_RESOURCE_TYPE]

    def get_ctag(self):
        raise NotImplementedError(self.getctag)

    def get_calendar_description(self):
        raise NotImplementedError(self.get_calendar_description)

    def get_calendar_color(self):
        raise NotImplementedError(self.get_calendar_color)

    def get_supported_calendar_components(self):
        """Return set of supported calendar components in this calendar.

        :return: iterable over component names
        """
        raise NotImplementedError(self.get_supported_calendar_components)


class PrincipalExtensions:
    """CalDAV-specific extensions to DAVPrincipal."""

    def get_calendar_home_set(self):
        """Get the calendar home set.

        :return: a set of URLs
        """
        raise NotImplementedError(self.get_calendar_home_set)

    def get_calendar_user_address_set(self):
        """Get the calendar user address set.

        :return: a set of URLs (usually mailto:...)
        """
        raise NotImplementedError(self.get_calendar_user_address_set)


class CalendarHomeSetProperty(DAVProperty):
    """calendar-home-set property

    See https://www.ietf.org/rfc/rfc4791.txt, section 6.2.1.
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-home-set'
    resource_type = '{DAV:}principal'
    in_allprops = False

    def get_value(self, resource, el):
        for href in resource.get_calendar_home_set():
            ET.SubElement(el, '{DAV:}href').text = href


class CalendarUserAddressSetProperty(DAVProperty):
    """calendar-user-address-set property

    See https://tools.ietf.org/html/rfc6638, section 2.4.1
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-user-address-set'
    resource_type = '{DAV:}principal'
    in_allprops = False

    def get_value(self, resource, el):
        for href in resource.get_calendar_user_address_set():
            ET.SubElement(el, '{DAV:}href').text = href


class CalendarDescriptionProperty(DAVProperty):
    """Provides calendar-description property.

    https://tools.ietf.org/html/rfc4791, section 5.2.1
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-description'
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, resource, el):
        el.text = resource.get_calendar_description()

    # TODO(jelmer): allow modification of this property
    # protected = True


class CalendarDataProperty(DAVProperty):
    """calendar-data property

    See https://tools.ietf.org/html/rfc4791, section 5.2.4

    Note that this is not technically a DAV property, and
    it is thus not registered in the regular webdav server.
    """

    name = '{%s}calendar-data' % NAMESPACE

    def get_value(self, resource, el):
        # TODO(jelmer): Support other kinds of calendar
        if resource.get_content_type() != 'text/calendar':
            raise KeyError
        # TODO(jelmer): Support subproperties
        # TODO(jelmer): Don't hardcode encoding
        el.text = b''.join(resource.get_body()).decode('utf-8')


class CalendarMultiGetReporter(davcommon.MultiGetReporter):

    name = '{urn:ietf:params:xml:ns:caldav}calendar-multiget'

    data_property_kls = CalendarDataProperty


class CalendarQueryReporter(DAVReporter):

    name = '{urn:ietf:params:xml:ns:caldav}calendar-query'

    def report(self, body, resources_by_hrefs, properties, base_href,
               base_resource, depth):
        # TODO(jelmer): Verify that resource is an addressbook
        requested = None
        filter = None
        for el in body:
            if el.tag == '{DAV:}prop':
                requested = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}filter':
                filter = el
            else:
                raise NotImplementedError(tag.name)
        properties = dict(properties)
        properties[CalendarDataProperty.name] = CalendarDataProperty()
        for (href, resource) in traverse_resource(
                base_resource, depth, base_href):
            # TODO: apply filter
            propstat = get_properties(
                resource, properties, requested)
            yield DAVStatus(href, '200 OK', propstat=list(propstat))


class CalendarColorProperty(DAVProperty):
    """calendar-color property

    This contains a HTML #RRGGBB color code, as CDATA.
    """

    name = '{http://apple.com/ns/ical/}calendar-color'
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, resource, el):
        el.text = resource.get_calendar_color()


class SupportedCalendarComponentSetProperty(DAVProperty):
    """supported-calendar-component-set property

    Set of supported calendar components by this calendar.

    See https://www.ietf.org/rfc/rfc4791.txt, section 5.2.3
    """

    name = '{urn:ietf:params:xml:ns:caldav}supported-calendar-component-set'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True

    def get_value(self, resource, el):
        for component in resource.get_supported_calendar_components():
            subel = ET.SubElement(el, '{urn:ietf:params:xml:ns:caldav}comp')
            subel.set('name', component)


class GetCTagProperty(DAVProperty):
    """getctag property

    """

    name = '{http://calendarserver.org/ns/}getctag'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True

    def get_value(self, resource, el):
        el.text = resource.get_ctag()
