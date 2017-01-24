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
import datetime
import defusedxml.ElementTree
import logging
import pytz
from xml.etree import ElementTree as ET

from icalendar.cal import Calendar as ICalendar
from icalendar.prop import vDDDTypes

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


def apply_prop_filter(el, comp, tzify):
    name = el.get('name')
    # From https://tools.ietf.org/html/rfc4791, 9.7.2:
    # A CALDAV:comp-filter is said to match if:

    # The CALDAV:prop-filter XML element contains a CALDAV:is-not-defined XML
    # element and no property of the type specified by the "name" attribute
    # exists in the enclosing calendar component;
    if [subel.tag for subel in el] == ['{urn:ietf:params:xml:ns:caldav}is-not-defined']:
        return name not in comp

    try:
        prop = comp[name]
    except KeyError:
        return False

    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
            if not apply_time_range(subel, prop, tzify):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}text-match':
            if not apply_text_match(subel, prop):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}param-filter':
            if not apply_param_filter(subel, prop):
                return False
    return True


def apply_text_match(el, value):
    raise NotImplementedError(apply_text_match)


def apply_param_filter(el, prop):
    name = el.get('name')
    if [subel.tag for subel in el] == ['{urn:ietf:params:xml:ns:caldav}is-not-defined']:
        return name not in prop.params

    try:
        value = prop.params[name]
    except KeyError:
        return False
    
    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}text-match':
            if not apply_text_match(subel, value):
                return False
        else:
            raise AssertionError('unknown tag %r in param-filter', subel.tag)
    return True


def _parse_time_range(el):
    start = el.get('start')
    end = el.get('end')
    # Either start OR end OR both need to be specified.
    # https://tools.ietf.org/html/rfc4791, section 9.9
    assert start is not None or end is not None
    if start is None:
        start = "00010101T000000Z"
    if end is None:
        end = "99991231T235959Z"
    start = vDDDTypes.from_ical(start)
    end = vDDDTypes.from_ical(end)
    assert end > start
    assert end.tzinfo
    assert start.tzinfo
    return (start, end)


def as_tz_aware_ts(dt, default_timezone):
    if not getattr(dt, 'time', None):
        dt = datetime.datetime.combine(dt, datetime.time())
    if dt.tzinfo is None:
        # TODO(jelmer): Use user-supplied tzid
        dt = dt.replace(tzinfo=default_timezone)
    assert dt.tzinfo
    return dt


def apply_time_range_vevent(start, end, comp, tzify):
    if not (end > tzify(comp['DTSTART'].dt)):
        return False

    if 'DTEND' in comp:
        if tzify(comp['DTEND'].dt) < tzify(comp['DTSTART'].dt):
            logging.debug('Invalid DTEND < DTSTART')
        return (start < tzify(comp['DTEND'].dt))

    if 'DURATION' in comp:
        return (start < tzify(comp['DTSTART'].dt) + comp['DURATION'].dt)
    if getattr(comp['DTSTART'].dt, 'time', None) is not None:
        return (start < (tzify(comp['DTSTART'].dt) + datetime.timedelta(1)))
    else:
        return (start <= comp['DTSTART'].dt)


def apply_time_range_vjournal(start, end, comp, tzify):
    raise NotImplementedError(apply_time_range_vjournal)


def apply_time_range_vtodo(start, end, comp, tzify):
    if 'DTSTART' in comp:
        if 'DURATION' in comp and not 'DUE' in comp:
            return (start <= tzify(comp['DTSTART'].dt)+comp['DURATION'].dt and
                    (end > tzify(comp['DTSTART'].dt) or
                     end >= tzify(comp['DTSTART'].dt)+comp['DURATION'].dt))
        elif 'DUE' in comp and not 'DURATION' in comp:
            return ((start <= tzify(comp['DTSTART'].dt) or start < tzify(comp['DUE'].dt)) and
                    (end > tzify(comp['DTSTART'].dt) or end < tzify(comp['DUE'].dt)))
        else:
            return (start <= tzify(comp['DTSTART'].dt) and end > tzify(comp['DTSTART'].dt))
    elif 'DUE' in comp:
        return (start < tzify(comp['DUE'].dt)) and (end >= tzify(comp['DUE'].dt))
    elif 'COMPLETED' in comp:
        if 'CREATED' in comp:
            return ((start <= tzify(comp['CREATED'].dt) or start <= tzify(comp['COMPLETED'].dt)) and
                    (end >= tzify(comp['CREATED'].dt) or end >= tzify(comp['COMPLETED'].dt)))
        else:
            return (start <= tzify(comp['COMPLETED'].dt) and end >= tzify(comp['COMPLETED'].dt))
    elif 'CREATED' in comp:
        return (end >= tzify(comp['CREATED'].dt))
    else:
        return True


def apply_time_range_vfreebusy(start, end, comp, tzify):
    raise NotImplementedError(apply_time_range_vfreebusy)


def apply_time_range_valarm(start, end, comp, tzify):
    raise NotImplementedError(apply_time_range_valarm)


def apply_time_range_comp(el, comp, tzify):
    # According to https://tools.ietf.org/html/rfc4791, section 9.9 these are
    # the properties to check.
    (start, end) = _parse_time_range(el)
    component_handlers = {
        'VEVENT': apply_time_range_vevent,
        'VTODO': apply_time_range_vtodo,
        'VJOURNAL': apply_time_range_vjournal,
        'VFREEBUSY': apply_time_range_vfreebusy,
        'VALARM': apply_time_range_valarm}
    try:
        component_handler = component_handlers[comp.name]
    except KeyError:
        logging.warning('unknown component %r in time-range filter',
                        comp.name)
        return False
    return component_handler(start, end, comp, tzify)


def apply_time_range(el, val, tzify):
    (start, end) = _parse_time_range(el)
    raise NotImplementedError(apply_time_range)


def apply_comp_filter(el, comp, tzify):
    """Compile a comp-filter element into a Python function.
    """
    name = el.get('name')
    # From https://tools.ietf.org/html/rfc4791, 9.7.1:
    # A CALDAV:comp-filter is said to match if:

    # 2. The CALDAV:comp-filter XML element contains a CALDAV:is-not-defined XML
    # element and the calendar object or calendar component type specified by
    # the "name" attribute does not exist in the current scope;
    if [subel.tag for subel in el] == ['{urn:ietf:params:xml:ns:caldav}is-not-defined']:
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
            if not any(apply_comp_filter(subel, c, tzify) for c in comp.subcomponents):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}prop-filter':
            if not apply_prop_filter(subel, comp, tzify):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
            if not apply_time_range_comp(subel, comp, tzify):
                return False
        else:
            raise AssertionError('unknown filter tag %r' % subel.tag)
    return True


def apply_filter(el, resource, tzify):
    """Compile a filter element into a Python function.
    """
    try:
        if resource.get_content_type() != 'text/calendar':
            return False
    except KeyError:
        return False
    if el is None:
        # Empty filter, let's not bother parsing
        return lambda x: True
    c = ICalendar.from_ical(b''.join(resource.get_body()))
    return apply_comp_filter(list(el)[0], c, tzify)


def extract_tzid(cal):
    return cal.subcomponents[0]['TZID']


class CalendarQueryReporter(DAVReporter):

    name = '{urn:ietf:params:xml:ns:caldav}calendar-query'

    def report(self, body, resources_by_hrefs, properties, base_href,
               base_resource, depth):
        # TODO(jelmer): Verify that resource is an addressbook
        requested = None
        filter_el = None
        tzid = None
        for el in body:
            if el.tag == '{DAV:}prop':
                requested = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}filter':
                filter_el = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}timezone':
                tzid = extract_tzid(ICalendar.from_ical(el.text))
            else:
                raise NotImplementedError(tag.name)
        if tzid is None:
            try:
                tzid = extract_tzid(ICalendar.from_ical(base_resource.get_calendar_timezone()))
            except KeyError:
                # TODO(jelmer): Or perhaps the servers' local timezone?
                tzid = 'UTC'
        tzify = lambda dt: as_tz_aware_ts(dt, pytz.timezone(tzid))
        properties = dict(properties)
        properties[CalendarDataProperty.name] = CalendarDataProperty()
        for (href, resource) in traverse_resource(
                base_resource, depth, base_href):
            if not apply_filter(filter_el, resource, tzify):
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
