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

from icalendar.cal import Calendar

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

    def get_calendar_timezone(self):
        """Return calendar timezone property.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.get_calendar_timezone)

    def set_calendar_timezone(self):
        """Set calendar timezone property.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.set_calendar_timezone)

    def get_supported_calendar_components(self):
        """Return set of supported calendar components in this calendar.

        :return: iterable over component names
        """
        raise NotImplementedError(self.get_supported_calendar_components)

    def get_supported_calendar_data_types(self):
        """Return supported calendar data types.

        :return: iterable over (content_type, version) tuples
        """
        raise NotImplementedError(self.get_supported_calendar_data_types)

    def get_min_date_time(self):
        """Return minimum datetime property.
        """
        raise NotImplementedError(self.get_min_date_time)

    def get_max_date_time(self):
        """Return maximum datetime property.
        """
        raise NotImplementedError(self.get_min_date_time)


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


def apply_prop_filter(el, comp):
    name = el.get('name')
    # From https://tools.ietf.org/html/rfc4791, 9.7.2:
    # A CALDAV:comp-filter is said to match if:

    # The CALDAV:prop-filter XML element contains a CALDAV:is-not-defined XML
    # element and no property of the type specified by the "name" attribute
    # exists in the enclosing calendar component;
    if list(el)[0].tag == '{urn:ietf:params:xml:ns:caldav}is-not-defined':
        return name not in comp

    try:
        val = comp[name]
    except KeyError:
        return False

    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
            if not apply_time_range(subel, val):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}text-match':
            if not apply_text_match(subel, val):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}param-filter':
            if not apply_param_filter(subel, val):
                return False
    return True


def apply_text_match(el, value):
    raise NotImplementedError(apply_text_match)


def apply_param_filter(el, value):
    raise NotImplementedError(apply_param_filter)


def apply_time_range_comp(el, comp):
    # According to https://tools.ietf.org/html/rfc4791, section 9.9 these are
    # the properties to check.
    TIME_RANGE_PROPERTIES = [
        'COMPLETED', 'CREATED', 'DTEND', 'DTSTAMP', 'DTSTART',
        'DUE', 'LAST-MODIFIED']
    raise NotImplementedError(apply_time_range_comp)


def apply_time_range(el, val):
    start = el.get('start')
    end = el.get('end')
    if start is None:
        start = "00010101T000000Z"
    if end is None:
        end = "99991231T235959Z"
    raise NotImplementedError(apply_time_range)


def apply_comp_filter(el, comp):
    """Compile a comp-filter element into a Python function.
    """
    name = el.get('name')
    # From https://tools.ietf.org/html/rfc4791, 9.7.1:
    # A CALDAV:comp-filter is said to match if:

    # 2. The CALDAV:comp-filter XML element contains a CALDAV:is-not-defined XML
    # element and the calendar object or calendar component type specified by
    # the "name" attribute does not exist in the current scope;
    if list(el)[0].tag == '{urn:ietf:params:xml:ns:caldav}is-not-defined':
        return comp.name != name

    # 1: The CALDAV:comp-filter XML element is empty and the calendar object or
    # calendar component type specified by the "name" attribute exists in the
    # current scope;
    if comp.name != name:
        return False

    # 3. The CALDAV:comp-filter XML element contains a CALDAV:time-range XML
    # element and at least one recurrence instance in the targeted calendar
    # component is scheduled to overlap the specified time range, and all
    # specified CALDAV:prop-filter and CALDAV:comp-filter child XML elements
    # also match the targeted calendar component;
    subchecks = []
    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}comp-filter':
            if not any(apply_comp_filter(subel, c) for c in comp.subcomponents):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}prop-filter':
            if not apply_prop_filter(subel, comp):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
            if not apply_time_range_comp(subel, comp):
                return False
        else:
            raise AssertionError('unknown filter tag %r' % subel.tag)
    return True


def apply_filter(el):
    """Compile a filter element into a Python function.
    """
    if el is None:
        # Empty filter, let's not bother parsing
        return lambda x: True
    c = Calendar.from_ical(b''.join(x.get_body()))
    return apply_comp_filter(list(el)[0], c)


class CalendarQueryReporter(DAVReporter):

    name = '{urn:ietf:params:xml:ns:caldav}calendar-query'

    def report(self, body, resources_by_hrefs, properties, base_href,
               base_resource, depth):
        # TODO(jelmer): Verify that resource is an addressbook
        requested = None
        filter_el = None
        for el in body:
            if el.tag == '{DAV:}prop':
                requested = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}filter':
                filter_el = el
            else:
                raise NotImplementedError(tag.name)
        filter_fn = compile_filter(filter_el)
        properties = dict(properties)
        properties[CalendarDataProperty.name] = CalendarDataProperty()
        for (href, resource) in traverse_resource(
                base_resource, depth, base_href):
            if not filter_fn(resource):
                continue
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


class SupportedCalendarDataProperty(DAVProperty):
    """supported-calendar-data property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.4
    """

    name = '{urn:ietf:params:xml:ns:caldav}supported-calendar-data'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True

    def get_value(self, resource, el):
        for (content_type, version) in (
                resource.get_supported_calendar_data_types()):
            subel = ET.SubElement(
                    el, '{urn:ietf:params:xml:ns:caldav}calendar-data')
            subel.set('content-type', content_type)
            subel.set('version', version)


class CalendarTimezoneProperty(DAVProperty):
    """calendar-timezone property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.2
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-timezone'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False

    def get_value(self, resource, el):
        el.text = resource.get_calendar_timezone()

    def set_value(self, resource, el):
        resource.set_calendar_timezone(el.text)


class MinDateTimeProperty(DAVProperty):
    """min-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.6
    """

    name = '{urn:ietf:params:xml:ns:caldav}min-date-time'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True

    def get_value(self, resource, el):
        el.text = resource.get_min_date_time()


class MaxDateTimeProperty(DAVProperty):
    """max-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.7
    """

    name = '{urn:ietf:params:xml:ns:caldav}max-date-time'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True

    def get_value(self, resource, el):
        el.text = resource.get_max_date_time()
