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

"""Simple CalDAV server.

https://tools.ietf.org/html/rfc4791
"""
import datetime
import itertools
import pytz

from .icalendar import (
    apply_time_range_vevent,
    as_tz_aware_ts,
)
from icalendar.cal import component_factory, Calendar as ICalendar, FreeBusy
from icalendar.prop import vDDDTypes, vPeriod, LocalTimezone

from xandikos import davcommon, webdav

ET = webdav.ET

PRODID = '-//Jelmer Vernooĳ//Xandikos//EN'
WELLKNOWN_CALDAV_PATH = "/.well-known/caldav"
EXTENDED_MKCOL_FEATURE = 'extended-mkcol'

NAMESPACE = 'urn:ietf:params:xml:ns:caldav'

# https://tools.ietf.org/html/rfc4791, section 4.2
CALENDAR_RESOURCE_TYPE = '{%s}calendar' % NAMESPACE

# TODO(jelmer): These resource types belong in scheduling.py
SCHEDULE_INBOX_RESOURCE_TYPE = '{%s}schedule-inbox' % NAMESPACE
SCHEDULE_OUTBOX_RESOURCE_TYPE = '{%s}schedule-outbox' % NAMESPACE

# Feature to advertise to indicate CalDAV support.
FEATURE = 'calendar-access'

TRANSPARENCY_TRANSPARENT = 'transparent'
TRANSPARENCY_OPAQUE = 'opaque'


class Calendar(webdav.Collection):

    resource_types = (webdav.Collection.resource_types +
                      [CALENDAR_RESOURCE_TYPE])

    def get_calendar_description(self):
        """Return the calendar description."""
        raise NotImplementedError(self.get_calendar_description)

    def get_calendar_color(self):
        """Return the calendar color."""
        raise NotImplementedError(self.get_calendar_color)

    def set_calendar_color(self, color):
        """Set the calendar color."""
        raise NotImplementedError(self.set_calendar_color)

    def get_calendar_order(self):
        """Return the calendar order."""
        raise NotImplementedError(self.get_calendar_order)

    def set_calendar_order(self, order):
        """Set the calendar order."""
        raise NotImplementedError(self.set_calendar_order)

    def get_calendar_timezone(self):
        """Return calendar timezone.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.get_calendar_timezone)

    def set_calendar_timezone(self, content):
        """Set calendar timezone.

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
        raise NotImplementedError(self.get_max_date_time)

    def get_max_instances(self):
        """Return maximum number of instances.
        """
        raise NotImplementedError(self.get_max_instances)

    def get_max_attendees_per_instance(self):
        """Return maximum number of attendees per instance.
        """
        raise NotImplementedError(self.get_max_attendees_per_instance)

    def get_max_resource_size(self):
        """Return max resource size."""
        raise NotImplementedError(self.get_max_resource_size)

    def get_max_attachments_per_resource(self):
        """Return max attachments per resource."""
        raise NotImplementedError(self.get_max_attachments_per_resource)

    def get_max_attachment_size(self):
        """Return max attachment size."""
        raise NotImplementedError(self.get_max_attachment_size)

    def get_schedule_calendar_transparency(self):
        """Get calendar transparency.

        Possible values are TRANSPARENCY_TRANSPARENT and TRANSPARENCY_OPAQUE
        """
        return TRANSPARENCY_OPAQUE

    def calendar_query(self, create_filter_fn):
        """Query for all the members of this calendar that match `filter`.

        This is a naive implementation; subclasses should ideally provide
        their own implementation that is faster.

        :param create_filter_fn: Callback that constructs a
            filter; takes a filter building class.
        :return: Iterator over name, resource objects
        """
        raise NotImplementedError(self.calendar_query)


class CalendarHomeSet(object):

    def get_managed_attachments_server_url(self):
        """Return the attachments server URL."""
        raise NotImplementedError(self.get_managed_attachments_server_url)


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

    name = '{%s}calendar-home-set' % NAMESPACE
    resource_type = '{DAV:}principal'
    in_allprops = False
    live = True

    def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_home_set():
            href = webdav.ensure_trailing_slash(href)
            el.append(webdav.create_href(href, base_href))


class CalendarDescriptionProperty(webdav.Property):
    """Provides calendar-description property.

    https://tools.ietf.org/html/rfc4791, section 5.2.1
    """

    name = '{%s}calendar-description' % NAMESPACE
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, base_href, resource, el, environ):
        el.text = resource.get_calendar_description()

    # TODO(jelmer): allow modification of this property
    def set_value(self, href, resource, el):
        raise NotImplementedError


def extract_from_calendar(incal, outcal, requested):
    """Extract requested components/properties from calendar.

    :param incal: Calendar to filter
    :param outcal: Calendar to write to
    :param requested: <calendar-data> element with requested
        components/properties
    :return: A Calendar
    """
    for tag in requested:
        if tag.tag == ('{%s}comp' % NAMESPACE):
            for insub in incal.subcomponents:
                if insub.name == tag.get('name'):
                    outsub = component_factory[insub.name]
                    outcal.add_component(outsub)
                    extract_from_calendar(insub, outsub, tag)
        elif tag.tag == ('{%s}prop' % NAMESPACE):
            outcal[tag.get('name')] = incal[tag.get('name')]
        elif tag.tag == ('{%s}expand' % NAMESPACE):
            # TODO(jelmer): https://github.com/jelmer/xandikos/issues/102
            raise NotImplementedError('expand is not yet implemented')
        elif tag.tag == ('{%s}limit-recurrence-set' % NAMESPACE):
            # TODO(jelmer): https://github.com/jelmer/xandikos/issues/103
            raise NotImplementedError(
                'limit-recurrence-set is not yet implemented')
        elif tag.tag == ('{%s}limit-freebusy-set' % NAMESPACE):
            # TODO(jelmer): https://github.com/jelmer/xandikos/issues/104
            raise NotImplementedError(
                'limit-freebusy-set is not yet implemented')
        else:
            raise AssertionError('invalid element %r' % tag)


class CalendarDataProperty(davcommon.SubbedProperty):
    """calendar-data property

    See https://tools.ietf.org/html/rfc4791, section 5.2.4

    Note that this is not technically a DAV property, and
    it is thus not registered in the regular webdav server.
    """

    name = '{%s}calendar-data' % NAMESPACE

    def supported_on(self, resource):
        return (resource.get_content_type() == 'text/calendar')

    def get_value_ext(self, base_href, resource, el, environ, requested):
        if len(requested) == 0:
            serialized_cal = b''.join(resource.get_body())
        else:
            c = ICalendar()
            calendar = calendar_from_resource(resource)
            if calendar is None:
                raise KeyError
            extract_from_calendar(calendar, c, requested)
            serialized_cal = c.to_ical()
        # TODO(jelmer): Don't hardcode encoding
        # TODO(jelmer): Strip invalid characters or raise an exception
        el.text = serialized_cal.decode('utf-8')


class CalendarOrderProperty(webdav.Property):
    """Provides calendar-order property.
    """

    name = '{http://apple.com/ns/ical/}calendar-order'
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, base_href, resource, el, environ):
        el.text = resource.get_calendar_order()

    def set_value(self, href, resource, el):
        resource.set_calendar_order(el.text)


class CalendarMultiGetReporter(davcommon.MultiGetReporter):

    name = '{%s}calendar-multiget' % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    data_property = CalendarDataProperty()


def parse_prop_filter(el, cls):
    name = el.get('name')

    # From https://tools.ietf.org/html/rfc4791, 9.7.2:
    # A CALDAV:comp-filter is said to match if:

    prop_filter = cls(name=name)

    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}is-not-defined':
            prop_filter.is_not_defined = True
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
            parse_time_range(subel, prop_filter.filter_time_range)
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}text-match':
            parse_text_match(subel, prop_filter.filter_text_match)
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}param-filter':
            parse_param_filter(subel, prop_filter.filter_parameter)
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}is-not-defined':
            pass
        else:
            raise AssertionError("unknown subelement %r" % subel.tag)
    return prop_filter


def parse_text_match(el, cls):
    collation = el.get('collation', 'i;ascii-casemap')
    negate_condition = el.get('negate-condition', 'no')

    return cls(
        el.text, collation=collation,
        negate_condition=(negate_condition == 'yes'))


def parse_param_filter(el, cls):
    name = el.get('name')

    param_filter = cls(name=name)

    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}is-not-defined':
            param_filter.is_not_defined = True
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}text-match':
            parse_text_match(subel, param_filter.filter_time_range)
        else:
            raise AssertionError('unknown tag %r in param-filter', subel.tag)
    return param_filter


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


def parse_time_range(el, cls):
    (start, end) = _parse_time_range(el)
    return cls(start, end)


def parse_comp_filter(el, cls):
    """Compile a comp-filter element into a Python function.
    """
    name = el.get('name')

    # From https://tools.ietf.org/html/rfc4791, 9.7.1:
    # A CALDAV:comp-filter is said to match if:

    comp_filter = cls(name=name)

    # 3. The CALDAV:comp-filter XML element contains a CALDAV:time-range XML
    # element and at least one recurrence instance in the targeted calendar
    # component is scheduled to overlap the specified time range, and all
    # specified CALDAV:prop-filter and CALDAV:comp-filter child XML elements
    # also match the targeted calendar component;
    for subel in el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}is-not-defined':
            comp_filter.is_not_defined = True
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}comp-filter':
            parse_comp_filter(subel, comp_filter.filter_subcomponent)
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}prop-filter':
            parse_prop_filter(subel, comp_filter.filter_property)
        elif subel.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
            parse_time_range(subel, comp_filter.filter_time_range)
        else:
            raise AssertionError('unknown filter tag %r' % subel.tag)
    return comp_filter


def parse_filter(filter_el, cls):
    for subel in filter_el:
        if subel.tag == '{urn:ietf:params:xml:ns:caldav}comp-filter':
            parse_comp_filter(subel, cls.filter_subcomponent)
        else:
            raise AssertionError('unknown filter tag %r' % subel.tag)
    return cls


def calendar_from_resource(resource):
    try:
        if resource.get_content_type() != 'text/calendar':
            return None
    except KeyError:
        return None
    return resource.file.calendar


def extract_tzid(cal):
    return cal.subcomponents[0]['TZID']


def get_pytz_from_text(tztext):
    tzid = extract_tzid(ICalendar.from_ical(tztext))
    return pytz.timezone(tzid)


def get_calendar_timezone(resource):
    try:
        tztext = resource.get_calendar_timezone()
    except KeyError:
        return LocalTimezone()
    else:
        return get_pytz_from_text(tztext)


class CalendarQueryReporter(webdav.Reporter):

    name = '{%s}calendar-query' % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    data_property = CalendarDataProperty()

    @webdav.multistatus
    def report(self, environ, body, resources_by_hrefs, properties, base_href,
               base_resource, depth):
        # TODO(jelmer): Verify that resource is a calendar
        requested = None
        filter_el = None
        tztext = None
        for el in body:
            if el.tag in ('{DAV:}prop', '{DAV:}propname', '{DAV:}allprop'):
                requested = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}filter':
                filter_el = el
            elif el.tag == '{urn:ietf:params:xml:ns:caldav}timezone':
                tztext = el.text
            else:
                raise webdav.BadRequestError(
                    'Unknown tag %s in report %s' % (el.tag, self.name))
        if tztext is not None:
            tz = get_pytz_from_text(tztext)
        else:
            tz = get_calendar_timezone(base_resource)

        def filter_fn(cls):
            return parse_filter(filter_el, cls(tz))

        def members(collection):
            return itertools.chain(
                collection.calendar_query(filter_fn),
                collection.subcollections())

        for (href, resource) in webdav.traverse_resource(
                base_resource, base_href, depth,
                members=members):
            # Ideally traverse_resource would only return the right things.
            if getattr(resource, 'content_type', None) == 'text/calendar':
                propstat = davcommon.get_properties_with_data(
                    self.data_property, href, resource, properties, environ,
                    requested)
                yield webdav.Status(href, '200 OK', propstat=list(propstat))


class CalendarColorProperty(webdav.Property):
    """calendar-color property

    This contains a HTML #RRGGBB color code, as CDATA.
    """

    name = '{http://apple.com/ns/ical/}calendar-color'
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, href, resource, el, environ):
        el.text = resource.get_calendar_color()

    def set_value(self, href, resource, el):
        resource.set_calendar_color(el.text)


class SupportedCalendarComponentSetProperty(webdav.Property):
    """supported-calendar-component-set property

    Set of supported calendar components by this calendar.

    See https://www.ietf.org/rfc/rfc4791.txt, section 5.2.3
    """

    name = '{%s}supported-calendar-component-set' % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE,
                     SCHEDULE_OUTBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        for component in resource.get_supported_calendar_components():
            subel = ET.SubElement(el, '{urn:ietf:params:xml:ns:caldav}comp')
            subel.set('name', component)


class SupportedCalendarDataProperty(webdav.Property):
    """supported-calendar-data property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.4
    """

    name = '{urn:ietf:params:xml:ns:caldav}supported-calendar-data'
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE,
                     SCHEDULE_OUTBOX_RESOURCE_TYPE)
    in_allprops = False

    def get_value(self, href, resource, el, environ):
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
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE)
    in_allprops = False

    def get_value(self, href, resource, el, environ):
        el.text = resource.get_calendar_timezone()

    def set_value(self, href, resource, el):
        if el is not None:
            resource.set_calendar_timezone(el.text)
        else:
            resource.set_calendar_timezone(None)


class MinDateTimeProperty(webdav.Property):
    """min-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.6
    """

    name = '{urn:ietf:params:xml:ns:caldav}min-date-time'
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE,
                     SCHEDULE_OUTBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = resource.get_min_date_time()


class MaxDateTimeProperty(webdav.Property):
    """max-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.7
    """

    name = '{urn:ietf:params:xml:ns:caldav}max-date-time'
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE,
                     SCHEDULE_OUTBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = resource.get_max_date_time()


class MaxInstancesProperty(webdav.Property):
    """max-instances property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.8
    """

    name = '{%s}max-instances' % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_instances())


class MaxAttendeesPerInstanceProperty(webdav.Property):
    """max-instances property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.9
    """

    name = '{%s}max-attendees-per-instance' % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE,
                     SCHEDULE_OUTBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_attendees_per_instance())


class MaxResourceSizeProperty(webdav.Property):
    """max-resource-size property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.5
    """

    name = '{%s}max-resource-size' % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE,
                     SCHEDULE_INBOX_RESOURCE_TYPE,
                     SCHEDULE_OUTBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_resource_size())


class MaxAttachmentsPerResourceProperty(webdav.Property):
    """max-attachments-per-resource property.

    https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html#rfc.section.6.3
    """

    name = '{%s}max-attachments-per-resource' % NAMESPACE
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_attachments_per_resource())


class MaxAttachmentSizeProperty(webdav.Property):
    """max-attachment-size property.

    https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html#rfc.section.6.2
    """

    name = '{%s}max-attachment-size' % NAMESPACE
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    live = True

    def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_attachment_size())


class ManagedAttachmentsServerURLProperty(webdav.Property):
    """managed-attachments-server-URL property.

    https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html#rfc.section.6.1
    """

    name = '{%s}managed-attachments-server-URL' % NAMESPACE
    in_allprops = False

    def get_value(self, base_href, resource, el, environ):
        # The RFC specifies that this property can be set on a calendar home
        # collection.
        # However, there is no matching resource type and we don't want to
        # force all resources to implement it. So we just check whether the
        # attribute is present.
        fn = getattr(resource, 'get_managed_attachments_server_url', None)
        if fn is None:
            raise KeyError
        href = fn()
        if href is not None:
            el.append(webdav.create_href(href, base_href))


class CalendarProxyReadForProperty(webdav.Property):
    """calendar-proxy-read-for property.

    See https://github.com/apple/ccs-calendarserver/blob/master/\
        doc/Extensions/caldav-proxy.txt, section 5.3.1.

    """
    name = '{http://calendarserver.org/ns/}calendar-proxy-read-for'
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False
    live = True

    def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_proxy_read_for():
            el.append(webdav.create_href(href, base_href))


class CalendarProxyWriteForProperty(webdav.Property):
    """calendar-proxy-write-for property.

    See https://github.com/apple/ccs-calendarserver/blob/master/\
        doc/Extensions/caldav-proxy.txt, section 5.3.2.

    """
    name = '{http://calendarserver.org/ns/}calendar-proxy-write-for'
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False
    live = True

    def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_proxy_write_for():
            el.append(webdav.create_href(href, base_href))


class ScheduleCalendarTransparencyProperty(webdav.Property):
    """schedule-calendar-transp property.

    See https://tools.ietf.org/html/rfc6638#section-9.1
    """
    name = '{%s}schedule-calendar-transp' % NAMESPACE
    in_allprops = False
    live = False
    resource_type = CALENDAR_RESOURCE_TYPE

    def get_value(self, base_href, resource, el, environ):
        transp = resource.get_schedule_calendar_transparency()
        if transp == TRANSPARENCY_TRANSPARENT:
            ET.SubElement(el, '{%s}transparent' % NAMESPACE)
        elif transp == TRANSPARENCY_OPAQUE:
            ET.SubElement(el, '{%s}opaque' % NAMESPACE)
        else:
            raise ValueError('Invalid transparency %s' % transp)


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
    resource_type = CALENDAR_RESOURCE_TYPE

    def report(self, environ, start_response, body, resources_by_hrefs,
               properties, base_href, base_resource, depth):
        requested = None
        for el in body:
            if el.tag == '{urn:ietf:params:xml:ns:caldav}time-range':
                requested = el
            else:
                raise AssertionError("unexpected XML element")
        tz = get_calendar_timezone(base_resource)

        def tzify(dt):
            return as_tz_aware_ts(dt, tz).astimezone(pytz.utc)
        (start, end) = _parse_time_range(requested)
        assert start.tzinfo
        assert end.tzinfo
        ret = ICalendar()
        ret['VERSION'] = '2.0'
        ret['PRODID'] = PRODID
        fb = FreeBusy()
        fb['DTSTAMP'] = vDDDTypes(tzify(datetime.datetime.now()))
        fb['DTSTART'] = vDDDTypes(start)
        fb['DTEND'] = vDDDTypes(end)
        fb['FREEBUSY'] = list(iter_freebusy(
            webdav.traverse_resource(base_resource, base_href, depth),
            start, end, tzify))
        ret.add_component(fb)
        start_response('200 OK', [])
        return [ret.to_ical()]


class MkcalendarMethod(webdav.Method):

    def handle(self, environ, start_response, app):
        try:
            content_type = environ['CONTENT_TYPE']
        except KeyError:
            base_content_type = None
        else:
            base_content_type, params = webdav.parse_type(content_type)
        if base_content_type not in (
            'text/xml', 'application/xml', None, 'text/plain'
        ):
            raise webdav.UnsupportedMediaType(content_type)
        href, path, resource = app._get_resource_from_environ(environ)
        if resource is not None:
            return webdav._send_simple_dav_error(
                environ, start_response,
                '403 Forbidden',
                error=ET.Element('{DAV:}resource-must-be-null'),
                description=('Something already exists at %r' % path))
        try:
            resource = app.backend.create_collection(path)
        except FileNotFoundError:
            start_response('409 Conflict', [])
            return []
        el = ET.Element('{DAV:}resourcetype')
        app.properties['{DAV:}resourcetype'].get_value(
            href, resource, el, environ)
        ET.SubElement(el, '{urn:ietf:params:xml:ns:caldav}calendar')
        app.properties['{DAV:}resourcetype'].set_value(href, resource, el)
        if base_content_type in ('text/xml', 'application/xml'):
            et = webdav._readXmlBody(
                environ, '{urn:ietf:params:xml:ns:caldav}mkcalendar')
            propstat = []
            for el in et:
                if el.tag != '{DAV:}set':
                    raise webdav.BadRequestError(
                        'Unknown tag %s in mkcalendar' % el.tag)
                propstat.extend(webdav.apply_modify_prop(
                    el, href, resource, app.properties))
                ret = ET.Element(
                    '{urn:ietf:params:xml:ns:carldav:}mkcalendar-response')
            for propstat_el in webdav.propstat_as_xml(propstat):
                ret.append(propstat_el)
            return webdav._send_xml_response(
                start_response, '201 Created', ret, webdav.DEFAULT_ENCODING)
        else:
            start_response('201 Created', [])
            return []
