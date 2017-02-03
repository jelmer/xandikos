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

"""Simple CalDAV server.

https://tools.ietf.org/html/rfc4791
"""
import datetime
import defusedxml.ElementTree
import logging
import pytz
from xml.etree import ElementTree as ET

from icalendar.cal import (
    Calendar as ICalendar,
    FreeBusy,
    )
from icalendar.prop import vDDDTypes, vPeriod

from xandikos import davcommon, webdav
from xandikos.webdav import (
    WebDAVApp,
    get_properties,
    traverse_resource,
    )

PRODID = '-//Jelmer Vernooij//Xandikos//EN'
WELLKNOWN_CALDAV_PATH = "/.well-known/caldav"

# https://tools.ietf.org/html/rfc4791, section 4.2
CALENDAR_RESOURCE_TYPE = '{urn:ietf:params:xml:ns:caldav}calendar'

NAMESPACE = 'urn:ietf:params:xml:ns:caldav'


class Calendar(webdav.Collection):

    resource_types = webdav.Collection.resource_types + [CALENDAR_RESOURCE_TYPE]

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


class CalendarHomeSetProperty(webdav.Property):
    """calendar-home-set property

    See https://www.ietf.org/rfc/rfc4791.txt, section 6.2.1.
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-home-set'
    resource_type = '{DAV:}principal'
    in_allprops = False
    live = True

    def get_value(self, resource, el):
        for href in resource.get_calendar_home_set():
            ET.SubElement(el, '{DAV:}href').text = href


class CalendarUserAddressSetProperty(webdav.Property):
    """calendar-user-address-set property

    See https://tools.ietf.org/html/rfc6638, section 2.4.1
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-user-address-set'
    resource_type = '{DAV:}principal'
    in_allprops = False

    def get_value(self, resource, el):
        for href in resource.get_calendar_user_address_set():
            ET.SubElement(el, '{DAV:}href').text = href


class CalendarDescriptionProperty(webdav.Property):
    """Provides calendar-description property.

    https://tools.ietf.org/html/rfc4791, section 5.2.1
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-description'
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, resource, el):
        el.text = resource.get_calendar_description()

    # TODO(jelmer): allow modification of this property
    # protected = True


class CalendarDataProperty(webdav.Property):
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
            if not apply_time_range_prop(subel, prop, tzify):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}text-match':
            if not apply_text_match(subel, prop):
                return False
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}param-filter':
            if not apply_param_filter(subel, prop):
                return False
    return True


# see https://tools.ietf.org/html/rfc4790

collations = {
        'i;ascii-casemap': lambda a, b: a.decode('ascii').upper() == b.decode('ascii').upper(),
        'i;octet': lambda a, b: a == b,
    }


def apply_text_match(el, value):
    collation = el.get('collation', 'i;ascii-casemap')
    negate_condition = el.get('negate-condition', 'no')
    matches = collations[collation](el.text, value)

    if negate_condition == 'yes':
        return (not matches)
    else:
        return matches


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


def apply_time_range_prop(el, val, tzify):
    (start, end) = _parse_time_range(el)
    raise NotImplementedError(apply_time_range_prop)


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


def calendar_from_resource(resource):
    try:
        if resource.get_content_type() != 'text/calendar':
            return None
    except KeyError:
        return None
    return ICalendar.from_ical(b''.join(resource.get_body()))


def apply_filter(el, resource, tzify):
    """Compile a filter element into a Python function.
    """
    if el is None:
        # Empty filter, let's not bother parsing
        return lambda x: True
    c = calendar_from_resource(resource)
    if c is None:
        return False
    return apply_comp_filter(list(el)[0], c, tzify)


def extract_tzid(cal):
    return cal.subcomponents[0]['TZID']


class CalendarQueryReporter(webdav.Reporter):

    name = '{urn:ietf:params:xml:ns:caldav}calendar-query'

    @webdav.multistatus
    def report(self, environ, body, resources_by_hrefs, properties, base_href,
               base_resource, depth):
        # TODO(jelmer): Verify that resource is an addressbook
        requested = None
        filter_el = None
        tztext = None
        for el in body:
            if el.tag == '{DAV:}prop':
                requested = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}filter':
                filter_el = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}timezone':
                tztext = el.text
            else:
                raise NotImplementedError(tag.name)
        if tztext is None:
            try:
                tztext = base_resource.get_calendar_timezone()
            except KeyError:
                tztext = None
        if tztext is not None:
            try:
                tzid = extract_tzid(ICalendar.from_ical(tztext))
            except KeyError:
                # TODO(jelmer): Or perhaps the servers' local timezone?
                tzid = 'UTC'
        else:
            tzid = 'UTC'
        tzify = lambda dt: as_tz_aware_ts(dt, pytz.timezone(tzid))
        properties = dict(properties)
        properties[CalendarDataProperty.name] = CalendarDataProperty()
        for (href, resource) in traverse_resource(
                base_resource, base_href, depth):
            if not apply_filter(filter_el, resource, tzify):
                continue
            propstat = get_properties(
                resource, properties, requested)
            yield webdav.Status(href, '200 OK', propstat=list(propstat))


class CalendarColorProperty(webdav.Property):
    """calendar-color property

    This contains a HTML #RRGGBB color code, as CDATA.
    """

    name = '{http://apple.com/ns/ical/}calendar-color'
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, resource, el):
        el.text = resource.get_calendar_color()


class SupportedCalendarComponentSetProperty(webdav.Property):
    """supported-calendar-component-set property

    Set of supported calendar components by this calendar.

    See https://www.ietf.org/rfc/rfc4791.txt, section 5.2.3
    """

    name = '{urn:ietf:params:xml:ns:caldav}supported-calendar-component-set'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True
    live = True

    def get_value(self, resource, el):
        for component in resource.get_supported_calendar_components():
            subel = ET.SubElement(el, '{urn:ietf:params:xml:ns:caldav}comp')
            subel.set('name', component)


class SupportedCalendarDataProperty(webdav.Property):
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


class CalendarTimezoneProperty(webdav.Property):
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


class MinDateTimeProperty(webdav.Property):
    """min-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.6
    """

    name = '{urn:ietf:params:xml:ns:caldav}min-date-time'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True
    live = True

    def get_value(self, resource, el):
        el.text = resource.get_min_date_time()


class MaxDateTimeProperty(webdav.Property):
    """max-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.7
    """

    name = '{urn:ietf:params:xml:ns:caldav}max-date-time'
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    protected = True
    live = True

    def get_value(self, resource, el):
        el.text = resource.get_max_date_time()


def map_freebusy(comp):
    transp = comp.get('TRANSP', 'OPAQUE')
    if transp == 'TRANSPARENT':
        return 'FREE'
    assert transp == 'OPAQUE', 'unknown transp %r' % transp
    status = comp.get('STATUS', 'CONFIRMED')
    if status == 'CONFIRMED':
        return 'BUSY'
    elif status == 'CANCELLED':
        return 'FREE'
    elif status == 'TENTATIVE':
        return 'BUSY-TENTATIVE'
    elif status.startswith('X-'):
        return status
    else:
        raise AssertionError('unknown status %r' % status)


def extract_freebusy(comp, tzify):
    kind = map_freebusy(comp)
    if kind == 'FREE':
        return None
    # TODO(jelmer): Convert to Zulu?
    if 'DTEND' in comp:
        ret = vPeriod((tzify(comp['DTSTART'].dt), tzify(comp['DTEND'].dt)))
    if 'DURATION' in comp:
        ret = vPeriod((tzify(comp['DTSTART'].dt), comp['DURATION'].dt))
    if kind != 'BUSY':
        ret.params['FBTYPE'] = kind
    return ret


def iter_freebusy(resources, start, end, tzify):
    for (href, resource) in resources:
        c = calendar_from_resource(resource)
        if c is None:
            continue
        if c.name != 'VCALENDAR':
            continue
        for comp in c.subcomponents:
            if comp.name == 'VEVENT':
                if apply_time_range_vevent(start, end, comp, tzify):
                    vp = extract_freebusy(comp, tzify)
                    if vp is not None:
                        yield vp


class FreeBusyQueryReporter(webdav.Reporter):
    """free-busy-query reporter.

    See https://tools.ietf.org/html/rfc4791, section 7.10
    """

    name = '{urn:ietf:params:xml:ns:caldav}free-busy-query'

    def report(self, environ, start_response, body, resources_by_hrefs, properties, base_href,
               base_resource, depth):
        requested = None
        for el in body:
            if el.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
                requested = el
            else:
                raise AssertionError("unexpected XML element")
        # TODO(jelmer): Right timezone?
        tzid = 'UTC'
        tzify = lambda dt: as_tz_aware_ts(dt, pytz.timezone(tzid))
        (start, end) = _parse_time_range(requested)
        ret = ICalendar()
        ret['VERSION'] = '2.0'
        ret['PRODID'] = PRODID
        fb = FreeBusy()
        fb['DTSTAMP'] = vDDDTypes(datetime.datetime.now())
        fb['DTSTART'] = start
        fb['DTEND'] = end
        fb['FREEBUSY'] = list(iter_freebusy(
            traverse_resource(base_resource, base_href, depth),
            start, end, tzify))
        ret.add_component(fb)
        start_response('200 OK', [])
        return [ret.to_ical()]
