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
import logging
from zoneinfo import ZoneInfo

from icalendar.cal import Calendar as ICalendar
from icalendar.cal import Component, FreeBusy, component_factory
from icalendar.prop import vDDDTypes, vPeriod

from . import davcommon, webdav
from .icalendar import (
    apply_time_range_vevent,
    apply_time_range_vavailability,
    as_tz_aware_ts,
    expand_calendar_rrule,
    limit_calendar_recurrence_set,
    limit_calendar_freebusy_set,
)

logger = logging.getLogger(__name__)

ET = webdav.ET

PRODID = "-//Jelmer Vernooĳ//Xandikos//EN"
WELLKNOWN_CALDAV_PATH = "/.well-known/caldav"
EXTENDED_MKCOL_FEATURE = "extended-mkcol"

NAMESPACE = "urn:ietf:params:xml:ns:caldav"

# https://tools.ietf.org/html/rfc4791, section 4.2
CALENDAR_RESOURCE_TYPE = "{%s}calendar" % NAMESPACE

SUBSCRIPTION_RESOURCE_TYPE = "{http://calendarserver.org/ns/}subscribed"

# Scheduling resource types (RFC 6638)
# These are defined here rather than in scheduling.py to avoid circular imports
SCHEDULE_INBOX_RESOURCE_TYPE = "{%s}schedule-inbox" % NAMESPACE
SCHEDULE_OUTBOX_RESOURCE_TYPE = "{%s}schedule-outbox" % NAMESPACE

# Feature to advertise to indicate CalDAV support.
FEATURE = "calendar-access"

TRANSPARENCY_TRANSPARENT = "transparent"
TRANSPARENCY_OPAQUE = "opaque"


class Calendar(webdav.Collection):
    resource_types = webdav.Collection.resource_types + [CALENDAR_RESOURCE_TYPE]

    def get_calendar_description(self) -> str:
        """Return the calendar description.

        This provides the value for the CALDAV:calendar-description property
        defined in RFC 4791 Section 5.2.1. It's a human-readable description
        of the calendar collection.
        """
        raise NotImplementedError(self.get_calendar_description)

    def set_calendar_description(self, description: str) -> None:
        """Set the calendar description.

        This sets the value for the CALDAV:calendar-description property
        defined in RFC 4791 Section 5.2.1.
        """
        raise NotImplementedError(self.set_calendar_description)

    def get_calendar_color(self) -> str:
        """Return the calendar color."""
        raise NotImplementedError(self.get_calendar_color)

    def set_calendar_color(self, color: str) -> None:
        """Set the calendar color."""
        raise NotImplementedError(self.set_calendar_color)

    def get_calendar_order(self) -> str:
        """Return the calendar order."""
        raise NotImplementedError(self.get_calendar_order)

    def set_calendar_order(self, order: str) -> None:
        """Set the calendar order."""
        raise NotImplementedError(self.set_calendar_order)

    def get_calendar_timezone(self) -> str:
        """Return calendar timezone.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.get_calendar_timezone)

    def set_calendar_timezone(self, content: str) -> None:
        """Set calendar timezone.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.set_calendar_timezone)

    def get_calendar_availability(self) -> str:
        """Return calendar availability.

        This should be an iCalendar object with one or more
        VAVAILABILITY components.
        """
        raise NotImplementedError(self.get_calendar_availability)

    def set_calendar_availability(self, content: str) -> None:
        """Set calendar availability.

        This should be an iCalendar object with one or more
        VAVAILABILITY components.
        """
        raise NotImplementedError(self.set_calendar_availability)

    def get_supported_calendar_components(self) -> str:
        """Return set of supported calendar components in this calendar.

        Returns: iterable over component names
        """
        raise NotImplementedError(self.get_supported_calendar_components)

    def get_supported_calendar_data_types(self) -> str:
        """Return supported calendar data types.

        Returns: iterable over (content_type, version) tuples
        """
        raise NotImplementedError(self.get_supported_calendar_data_types)

    def get_min_date_time(self):
        """Return minimum datetime property."""
        raise NotImplementedError(self.get_min_date_time)

    def get_max_date_time(self):
        """Return maximum datetime property."""
        raise NotImplementedError(self.get_max_date_time)

    def get_max_instances(self):
        """Return maximum number of instances."""
        raise NotImplementedError(self.get_max_instances)

    def get_max_attendees_per_instance(self):
        """Return maximum number of attendees per instance."""
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

        Args:
          create_filter_fn: Callback that constructs a
            filter; takes a filter building class.
        Returns: Iterator over name, resource objects
        """
        raise NotImplementedError(self.calendar_query)

    def get_xmpp_server(self):
        raise NotImplementedError(self.get_xmpp_server)

    def get_xmpp_heartbeat(self):
        raise NotImplementedError(self.get_xmpp_heartbeat)

    def get_xmpp_uri(self):
        raise NotImplementedError(self.get_xmpp_uri)

    def get_created_by(self):
        raise NotImplementedError(self.get_created_by)

    def get_updated_by(self):
        raise NotImplementedError(self.get_updated_by)


class Subscription:
    resource_types = webdav.Collection.resource_types + [SUBSCRIPTION_RESOURCE_TYPE]

    def get_source_url(self):
        """Get the source URL for this calendar."""
        raise NotImplementedError(self.get_source_url)

    def set_source_url(self, url):
        """Set the source URL for this calendar."""
        raise NotImplementedError(self.set_source_url)

    def get_calendar_description(self):
        """Return the calendar description."""
        raise NotImplementedError(self.get_calendar_description)

    def get_calendar_color(self):
        """Return the calendar color."""
        raise NotImplementedError(self.get_calendar_color)

    def set_calendar_color(self, color):
        """Set the calendar color."""
        raise NotImplementedError(self.set_calendar_color)

    def get_supported_calendar_components(self):
        """Return set of supported calendar components in this calendar.

        Returns: iterable over component names
        """
        raise NotImplementedError(self.get_supported_calendar_components)


class CalendarHomeSet:
    def get_managed_attachments_server_url(self):
        """Return the attachments server URL."""
        raise NotImplementedError(self.get_managed_attachments_server_url)


class PrincipalExtensions:
    """CalDAV-specific extensions to DAVPrincipal."""

    def get_calendar_home_set(self):
        """Get the calendar home set.

        Returns: a set of URLs
        """
        raise NotImplementedError(self.get_calendar_home_set)

    def get_calendar_user_address_set(self):
        """Get the calendar user address set.

        Returns: a set of URLs (usually mailto:...)
        """
        raise NotImplementedError(self.get_calendar_user_address_set)


class CalendarHomeSetProperty(webdav.Property):
    """calendar-home-set property.

    See https://www.ietf.org/rfc/rfc4791.txt, section 6.2.1.
    """

    name = "{%s}calendar-home-set" % NAMESPACE
    resource_type = "{DAV:}principal"
    in_allprops = False
    live = True

    async def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_home_set():
            href = webdav.ensure_trailing_slash(href)
            el.append(webdav.create_href(href, base_href))


class CalendarDescriptionProperty(webdav.Property):
    """Provides calendar-description property.

    https://tools.ietf.org/html/rfc4791, section 5.2.1
    """

    name = "{%s}calendar-description" % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE, SUBSCRIPTION_RESOURCE_TYPE)

    async def get_value(self, base_href, resource, el, environ):
        el.text = resource.get_calendar_description()

    async def set_value(self, href, resource, el):
        resource.set_calendar_description(el.text)


def _extract_from_component(incomp: Component, outcomp: Component, requested) -> None:
    """Extract specific properties from a calendar event.

    Args:
      incomp: Incoming component
      outcomp: Outcoming component
      requested: Which components should be included
    """
    for tag in requested:
        if tag.tag == ("{%s}comp" % NAMESPACE):
            for insub in incomp.subcomponents:
                if insub.name == tag.get("name"):
                    outsub = component_factory[insub.name]()
                    outcomp.add_component(outsub)
                    _extract_from_component(insub, outsub, tag)
        elif tag.tag == ("{%s}prop" % NAMESPACE):
            outcomp[tag.get("name")] = incomp[tag.get("name")]
        elif tag.tag == ("{%s}allprop" % NAMESPACE):
            for propname in incomp:
                outcomp[propname] = incomp[propname]
        elif tag.tag == ("{%s}allcomp" % NAMESPACE):
            for insub in incomp.subcomponents:
                outsub = component_factory[insub.name]()
                outcomp.add_component(outsub)
                _extract_from_component(insub, outsub, tag)
        else:
            raise AssertionError(f"invalid element {tag!r}")


def extract_from_calendar(incal, requested):
    """Extract requested components/properties from calendar.

    Args:
      incal: Calendar to filter
      requested: <calendar-data> element with requested
        components/properties
    """
    for tag in requested:
        if tag.tag == ("{%s}comp" % NAMESPACE):
            if incal.name == tag.get("name"):
                c = ICalendar()
                _extract_from_component(incal, c, tag)
                incal = c
        elif tag.tag == ("{%s}expand" % NAMESPACE):
            (start, end) = _parse_time_range(tag)
            incal = expand_calendar_rrule(incal, start, end)
        elif tag.tag == ("{%s}limit-recurrence-set" % NAMESPACE):
            (start, end) = _parse_time_range(tag)
            incal = limit_calendar_recurrence_set(incal, start, end)
        elif tag.tag == ("{%s}limit-freebusy-set" % NAMESPACE):
            (start, end) = _parse_time_range(tag)
            incal = limit_calendar_freebusy_set(incal, start, end)
        else:
            raise AssertionError(f"invalid element {tag!r}")
    return incal


class CalendarDataProperty(davcommon.SubbedProperty):
    """calendar-data property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.4

    Note that this is not technically a DAV property, and
    it is thus not registered in the regular webdav server.
    """

    name = "{%s}calendar-data" % NAMESPACE

    def supported_on(self, resource):
        try:
            return resource.get_content_type() == "text/calendar"
        except KeyError:
            # Resource doesn't have a content type
            return False

    async def get_value_ext(self, base_href, resource, el, environ, requested):
        if len(requested) == 0:
            serialized_cal = b"".join(await resource.get_body())
        else:
            calendar = await calendar_from_resource(resource)
            if calendar is None:
                raise KeyError
            c = extract_from_calendar(calendar, requested)
            serialized_cal = c.to_ical()
        # UTF-8 encoding is required by RFC 5545 (iCalendar format)
        # decode() will raise UnicodeDecodeError on invalid UTF-8
        el.text = serialized_cal.decode("utf-8")


class CalendarOrderProperty(webdav.Property):
    """Provides calendar-order property."""

    name = "{http://apple.com/ns/ical/}calendar-order"
    resource_type = CALENDAR_RESOURCE_TYPE

    async def get_value(self, base_href, resource, el, environ):
        el.text = resource.get_calendar_order()

    async def set_value(self, href, resource, el):
        resource.set_calendar_order(el.text)


class CalendarMultiGetReporter(davcommon.MultiGetReporter):
    # RFC 4791 Section 7.9 (CalDAV calendar-multiget) specifies:
    #   "the 'Depth' header MUST be ignored by the server and SHOULD NOT be
    #   sent by the client."
    #
    # Therefore, we do NOT validate the Depth header for CalDAV multiget
    # operations. The base class implementation handles the request logic,
    # and any Depth header value is simply ignored as per the RFC.
    #
    # Note: Some CalDAV client libraries
    # send Depth: 1, which is against the RFC's recommendation but should
    # not cause the request to fail.
    name = "{%s}calendar-multiget" % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    data_property = CalendarDataProperty()


def parse_prop_filter(el, cls):
    name = el.get("name")

    # From https://tools.ietf.org/html/rfc4791, 9.7.2:
    # A CALDAV:comp-filter is said to match if:

    prop_filter = cls(name=name)

    for subel in el:
        if subel.tag == "{urn:ietf:params:xml:ns:caldav}is-not-defined":
            prop_filter.is_not_defined = True
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}time-range":
            parse_time_range(subel, prop_filter.filter_time_range)
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}text-match":
            parse_text_match(subel, prop_filter.filter_text_match)
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}param-filter":
            parse_param_filter(subel, prop_filter.filter_parameter)
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}is-not-defined":
            pass
        else:
            raise AssertionError(f"unknown subelement {subel.tag!r}")
    return prop_filter


def parse_text_match(el, cls):
    collation = el.get("collation", "i;ascii-casemap")
    negate_condition = el.get("negate-condition", "no")

    return cls(
        el.text,
        collation=collation,
        negate_condition=(negate_condition == "yes"),
    )


def parse_param_filter(el, cls):
    name = el.get("name")

    param_filter = cls(name=name)

    for subel in el:
        if subel.tag == "{urn:ietf:params:xml:ns:caldav}is-not-defined":
            param_filter.is_not_defined = True
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}text-match":
            parse_text_match(subel, param_filter.filter_time_range)
        else:
            raise AssertionError("unknown tag %r in param-filter", subel.tag)
    return param_filter


def _parse_time_range(el):
    start = el.get("start")
    end = el.get("end")
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
    return (start, end)


def parse_time_range(el, cls):
    (start, end) = _parse_time_range(el)
    return cls(start, end)


def parse_comp_filter(el: ET.Element, cls):
    """Compile a comp-filter element into a Python function."""
    name = el.get("name")

    # From https://tools.ietf.org/html/rfc4791, 9.7.1:
    # A CALDAV:comp-filter is said to match if:

    comp_filter = cls(name=name)

    # 3. The CALDAV:comp-filter XML element contains a CALDAV:time-range XML
    # element and at least one recurrence instance in the targeted calendar
    # component is scheduled to overlap the specified time range, and all
    # specified CALDAV:prop-filter and CALDAV:comp-filter child XML elements
    # also match the targeted calendar component;
    for subel in el:
        if subel.tag == "{urn:ietf:params:xml:ns:caldav}is-not-defined":
            comp_filter.is_not_defined = True
        if subel.tag == "{urn:ietf:params:xml:ns:caldav}comp-filter":
            parse_comp_filter(subel, comp_filter.filter_subcomponent)
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}prop-filter":
            parse_prop_filter(subel, comp_filter.filter_property)
        elif subel.tag == "{urn:ietf:params:xml:ns:caldav}time-range":
            parse_time_range(subel, comp_filter.filter_time_range)
        else:
            raise AssertionError(f"unknown filter tag {subel.tag!r}")
    return comp_filter


def parse_filter(filter_el: ET.Element, cls):
    for subel in filter_el:
        if subel.tag == "{urn:ietf:params:xml:ns:caldav}comp-filter":
            parse_comp_filter(subel, cls.filter_subcomponent)
        else:
            raise AssertionError(f"unknown filter tag {subel.tag!r}")
    return cls


async def calendar_from_resource(resource, start=None, end=None):
    """Get calendar from resource, optionally with expansion.

    Args:
        resource: Calendar resource
        start: Start datetime for expansion (optional)
        end: End datetime for expansion (optional)

    Returns:
        Calendar object, expanded if start/end provided
    """
    try:
        if resource.get_content_type() != "text/calendar":
            return None
    except KeyError:
        return None
    file = await resource.get_file()
    if start is not None or end is not None:
        return file.get_expanded_calendar(start, end)
    return file.calendar


def extract_tzid(cal):
    return cal.subcomponents[0]["TZID"]


def get_timezone_from_text(tztext):
    tzid = extract_tzid(ICalendar.from_ical(tztext))
    return ZoneInfo(tzid)


def get_calendar_timezone(resource: Calendar):
    try:
        tztext = resource.get_calendar_timezone()
    except KeyError:
        now = datetime.datetime.now()
        local_now = now.astimezone()
        return local_now.tzinfo
    else:
        return get_timezone_from_text(tztext)


class CalendarQueryReporter(webdav.Reporter):
    name = "{%s}calendar-query" % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    data_property = CalendarDataProperty()

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
        # Note: Resource type validation is performed by the REPORT handler
        # via supported_on() before this method is called
        requested = None
        filter_el = None
        tztext = None
        for el in body:
            if el.tag in ("{DAV:}prop", "{DAV:}propname", "{DAV:}allprop"):
                requested = el
            elif el.tag == "{urn:ietf:params:xml:ns:caldav}filter":
                filter_el = el
            elif el.tag == "{urn:ietf:params:xml:ns:caldav}timezone":
                tztext = el.text
            else:
                webdav.nonfatal_bad_request(
                    f"Unknown tag {el.tag} in report {self.name}", strict
                )
        if requested is None:
            # The CalDAV RFC says that behaviour mimics that of PROPFIND,
            # and the WebDAV RFC says that no body implies {DAV}allprop
            # This isn't exactly an empty body, but close enough.
            requested = ET.Element("{DAV:}allprop")
        if tztext is not None:
            tz = get_timezone_from_text(tztext)
        else:
            tz = get_calendar_timezone(base_resource)

        def filter_fn(cls):
            return parse_filter(filter_el, cls(tz))

        def members(collection):
            return itertools.chain(
                collection.calendar_query(filter_fn),
                collection.subcollections(),
            )

        async for href, resource in webdav.traverse_resource(
            base_resource, base_href, depth, members=members
        ):
            # Ideally traverse_resource would only return the right things.
            if getattr(resource, "content_type", None) == "text/calendar":
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


class CalendarColorProperty(webdav.Property):
    """calendar-color property.

    This contains a HTML #RRGGBB color code, as CDATA.
    """

    name = "{http://apple.com/ns/ical/}calendar-color"
    resource_type = (CALENDAR_RESOURCE_TYPE, SUBSCRIPTION_RESOURCE_TYPE)

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_calendar_color()

    async def set_value(self, href, resource, el):
        resource.set_calendar_color(el.text)


class CreatedByProperty(webdav.Property):
    """created-by property."""

    name = "{http://calendarserver.org/ns/}created-by"
    resource_type = CALENDAR_RESOURCE_TYPE

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_created_by()


class UpdatedByProperty(webdav.Property):
    """updated-by property."""

    name = "{http://calendarserver.org/ns/}updated-by"
    resource_type = CALENDAR_RESOURCE_TYPE

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_updated_by()


class SupportedCalendarComponentSetProperty(webdav.Property):
    """supported-calendar-component-set property.

    Set of supported calendar components by this calendar.

    See https://www.ietf.org/rfc/rfc4791.txt, section 5.2.3
    """

    name = "{%s}supported-calendar-component-set" % NAMESPACE
    resource_type = (
        CALENDAR_RESOURCE_TYPE,
        SCHEDULE_INBOX_RESOURCE_TYPE,
        SCHEDULE_OUTBOX_RESOURCE_TYPE,
        SUBSCRIPTION_RESOURCE_TYPE,
    )
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        for component in resource.get_supported_calendar_components():
            subel = ET.SubElement(el, "{urn:ietf:params:xml:ns:caldav}comp")
            subel.set("name", component)


class SupportedCalendarDataProperty(webdav.Property):
    """supported-calendar-data property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.4
    """

    name = "{urn:ietf:params:xml:ns:caldav}supported-calendar-data"
    resource_type = (
        CALENDAR_RESOURCE_TYPE,
        SCHEDULE_INBOX_RESOURCE_TYPE,
        SCHEDULE_OUTBOX_RESOURCE_TYPE,
    )
    in_allprops = False

    async def get_value(self, href, resource, el, environ):
        for (
            content_type,
            version,
        ) in resource.get_supported_calendar_data_types():
            subel = ET.SubElement(el, "{urn:ietf:params:xml:ns:caldav}calendar-data")
            subel.set("content-type", content_type)
            subel.set("version", version)


class CalendarTimezoneProperty(webdav.Property):
    """calendar-timezone property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.2
    """

    name = "{urn:ietf:params:xml:ns:caldav}calendar-timezone"
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    in_allprops = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_calendar_timezone()

    async def set_value(self, href, resource, el):
        if el is not None:
            resource.set_calendar_timezone(el.text)
        else:
            resource.set_calendar_timezone(None)


class CalendarAvailabilityProperty(webdav.Property):
    """calendar-availability property.

    See https://tools.ietf.org/html/rfc7953, section 5.1
    """

    name = "{urn:ietf:params:xml:ns:caldav}calendar-availability"
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    in_allprops = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_calendar_availability()

    async def set_value(self, href, resource, el):
        if el is not None:
            resource.set_calendar_availability(el.text)
        else:
            resource.set_calendar_availability(None)


class MinDateTimeProperty(webdav.Property):
    """min-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.6
    """

    name = "{urn:ietf:params:xml:ns:caldav}min-date-time"
    resource_type = (
        CALENDAR_RESOURCE_TYPE,
        SCHEDULE_INBOX_RESOURCE_TYPE,
        SCHEDULE_OUTBOX_RESOURCE_TYPE,
    )
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_min_date_time()


class MaxDateTimeProperty(webdav.Property):
    """max-date-time property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.7
    """

    name = "{urn:ietf:params:xml:ns:caldav}max-date-time"
    resource_type = (
        CALENDAR_RESOURCE_TYPE,
        SCHEDULE_INBOX_RESOURCE_TYPE,
        SCHEDULE_OUTBOX_RESOURCE_TYPE,
    )
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_max_date_time()


class MaxInstancesProperty(webdav.Property):
    """max-instances property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.8
    """

    name = "{%s}max-instances" % NAMESPACE
    resource_type = (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_instances())


class MaxAttendeesPerInstanceProperty(webdav.Property):
    """max-instances property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.9
    """

    name = "{%s}max-attendees-per-instance" % NAMESPACE
    resource_type = (
        CALENDAR_RESOURCE_TYPE,
        SCHEDULE_INBOX_RESOURCE_TYPE,
        SCHEDULE_OUTBOX_RESOURCE_TYPE,
    )
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_attendees_per_instance())


class MaxResourceSizeProperty(webdav.Property):
    """max-resource-size property.

    See https://tools.ietf.org/html/rfc4791, section 5.2.5
    """

    name = "{%s}max-resource-size" % NAMESPACE
    resource_type = (
        CALENDAR_RESOURCE_TYPE,
        SCHEDULE_INBOX_RESOURCE_TYPE,
        SCHEDULE_OUTBOX_RESOURCE_TYPE,
    )
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_resource_size())


class MaxAttachmentsPerResourceProperty(webdav.Property):
    """max-attachments-per-resource property.

    https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html#rfc.section.6.3
    """

    name = "{%s}max-attachments-per-resource" % NAMESPACE
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_attachments_per_resource())


class MaxAttachmentSizeProperty(webdav.Property):
    """max-attachment-size property.

    https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html#rfc.section.6.2
    """

    name = "{%s}max-attachment-size" % NAMESPACE
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_max_attachment_size())


class ManagedAttachmentsServerURLProperty(webdav.Property):
    """managed-attachments-server-URL property.

    https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html#rfc.section.6.1
    """

    name = "{%s}managed-attachments-server-URL" % NAMESPACE
    in_allprops = False

    async def get_value(self, base_href, resource, el, environ):
        # The RFC specifies that this property can be set on a calendar home
        # collection.
        # However, there is no matching resource type and we don't want to
        # force all resources to implement it. So we just check whether the
        # attribute is present.
        fn = getattr(resource, "get_managed_attachments_server_url", None)
        if fn is None:
            raise KeyError
        href = fn()
        if href is not None:
            el.append(webdav.create_href(href, base_href))


class SourceProperty(webdav.Property):
    """source property."""

    name = "{http://calendarserver.org/ns/}source"
    resource_type = SUBSCRIPTION_RESOURCE_TYPE
    in_allprops = True
    live = False

    async def get_value(self, base_href, resource, el, environ):
        el.append(webdav.create_href(resource.get_source_url(), base_href))

    async def set_value(self, href, resource, el):
        raise NotImplementedError(self.set_value)


class CalendarProxyReadForProperty(webdav.Property):
    """calendar-proxy-read-for property.

    See https://github.com/apple/ccs-calendarserver/blob/master/\
        doc/Extensions/caldav-proxy.txt, section 5.3.1.

    """

    name = "{http://calendarserver.org/ns/}calendar-proxy-read-for"
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_proxy_read_for():
            el.append(webdav.create_href(href, base_href))


class CalendarProxyWriteForProperty(webdav.Property):
    """calendar-proxy-write-for property.

    See https://github.com/apple/ccs-calendarserver/blob/master/\
        doc/Extensions/caldav-proxy.txt, section 5.3.2.

    """

    name = "{http://calendarserver.org/ns/}calendar-proxy-write-for"
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_proxy_write_for():
            el.append(webdav.create_href(href, base_href))


class ScheduleCalendarTransparencyProperty(webdav.Property):
    """schedule-calendar-transp property.

    See https://tools.ietf.org/html/rfc6638#section-9.1
    """

    name = "{%s}schedule-calendar-transp" % NAMESPACE
    in_allprops = False
    live = False
    resource_type = CALENDAR_RESOURCE_TYPE

    async def get_value(self, base_href, resource, el, environ):
        transp = resource.get_schedule_calendar_transparency()
        if transp == TRANSPARENCY_TRANSPARENT:
            ET.SubElement(el, "{%s}transparent" % NAMESPACE)
        elif transp == TRANSPARENCY_OPAQUE:
            ET.SubElement(el, "{%s}opaque" % NAMESPACE)
        else:
            raise ValueError(f"Invalid transparency {transp}")


def map_freebusy(comp):
    transp = comp.get("TRANSP", "OPAQUE")
    if transp == "TRANSPARENT":
        return "FREE"
    assert transp == "OPAQUE", f"unknown transp {transp!r}"
    status = comp.get("STATUS", "CONFIRMED")
    if status == "CONFIRMED":
        return "BUSY"
    elif status == "CANCELLED":
        return "FREE"
    elif status == "TENTATIVE":
        return "BUSY-TENTATIVE"
    elif status.startswith("X-"):
        return status
    else:
        raise AssertionError(f"unknown status {status!r}")


def extract_freebusy(comp, tzify):
    kind = map_freebusy(comp)
    if kind == "FREE":
        return None
    if "DTEND" in comp:
        ret = vPeriod((tzify(comp["DTSTART"].dt), tzify(comp["DTEND"].dt)))
    if "DURATION" in comp:
        ret = vPeriod((tzify(comp["DTSTART"].dt), comp["DURATION"].dt))
    if kind != "BUSY":
        ret.params["FBTYPE"] = kind
    return ret


def extract_availability_periods(vavail_comp, tzify, start, end):
    """Extract busy and free periods from a VAVAILABILITY component.

    Args:
        vavail_comp: VAVAILABILITY component
        tzify: Function to convert datetime to UTC
        start: Query start time
        end: Query end time

    Yields:
        vPeriod objects representing busy/free periods
    """
    # Get the overall availability time range
    dtstart = vavail_comp.get("DTSTART")
    dtend = vavail_comp.get("DTEND")
    duration = vavail_comp.get("DURATION")

    if not dtstart:
        return

    avail_start = tzify(dtstart.dt)

    if dtend:
        avail_end = tzify(dtend.dt)
    elif duration:
        avail_end = avail_start + duration.dt
    else:
        # No end time, availability continues indefinitely
        avail_end = end

    # Check if availability period overlaps with query range
    if avail_end <= start or avail_start >= end:
        return

    # Clip to query range
    period_start = max(avail_start, start)
    period_end = min(avail_end, end)

    # Get the default busy type from BUSYTYPE property
    busytype = vavail_comp.get("BUSYTYPE", "BUSY-UNAVAILABLE")

    # First, yield the overall period as busy (will be overridden by AVAILABLE subcomponents)
    busy_period = vPeriod((period_start, period_end))
    if busytype != "BUSY":
        busy_period.params["FBTYPE"] = busytype
    yield ("BUSY", busy_period)

    # Process AVAILABLE subcomponents to mark free time
    for subcomp in vavail_comp.subcomponents:
        if subcomp.name == "AVAILABLE":
            sub_dtstart = subcomp.get("DTSTART")
            sub_dtend = subcomp.get("DTEND")
            sub_duration = subcomp.get("DURATION")

            if not sub_dtstart:
                continue

            sub_start = tzify(sub_dtstart.dt)

            if sub_dtend:
                sub_end = tzify(sub_dtend.dt)
            elif sub_duration:
                sub_end = sub_start + sub_duration.dt
            else:
                # No end time for AVAILABLE period
                continue

            # Check if AVAILABLE period overlaps with query range and availability range
            if sub_end <= max(period_start, start) or sub_start >= min(period_end, end):
                continue

            # Clip to both query range and availability range
            free_start = max(sub_start, period_start, start)
            free_end = min(sub_end, period_end, end)

            # Yield free period
            free_period = vPeriod((free_start, free_end))
            yield ("FREE", free_period)


def process_vavailability_components(components, start, end, tzify):
    """Process VAVAILABILITY components according to RFC 7953 priority rules.

    This implements the algorithm from RFC 7953 section 4.4:
    1. Initially mark the entire period as free
    2. Process VAVAILABILITY in priority order (lowest to highest)
    3. Apply AVAILABLE subcomponents to mark free time
    4. Return the resulting busy/free periods

    Args:
        components: List of VAVAILABILITY components
        start: Query start time (UTC)
        end: Query end time (UTC)
        tzify: Function to convert datetime to UTC

    Returns:
        List of (start, end, fbtype) tuples representing busy/free periods
    """
    # Create a timeline to track busy/free periods
    # Each entry is (start_time, end_time, fbtype, priority)
    timeline = []

    # Sort components by priority (0=undefined, 9=lowest, 1=highest)
    # Process from lowest priority to highest so higher priority can override
    def get_priority(comp):
        priority = comp.get("PRIORITY", 0)
        if isinstance(priority, int):
            parsed_priority = priority
        elif isinstance(priority, str):
            try:
                parsed_priority = int(priority)
            except ValueError:
                logger.warning("Invalid PRIORITY value %r, defaulting to 0", priority)
                return 0  # Default to undefined priority
        else:
            # It's an iCalendar property value
            try:
                parsed_priority = int(priority.to_ical().decode("utf-8"))
            except ValueError:
                logger.warning("Invalid PRIORITY value %r, defaulting to 0", priority)
                return 0  # Default to undefined priority

        # Check priority range (RFC 7953: 1-9, 0=undefined)
        if parsed_priority < 0 or parsed_priority > 9:
            logger.warning("Invalid PRIORITY value %r, defaulting to 0", priority)
            return 0

        return parsed_priority

    sorted_components = sorted(components, key=get_priority, reverse=True)

    for vavail in sorted_components:
        priority = get_priority(vavail)

        # Get the overall availability time range
        dtstart = vavail.get("DTSTART")
        dtend = vavail.get("DTEND")
        duration = vavail.get("DURATION")

        if not dtstart:
            continue

        avail_start = tzify(dtstart.dt)

        if dtend:
            avail_end = tzify(dtend.dt)
        elif duration:
            avail_end = avail_start + duration.dt
        else:
            # No end time, availability continues indefinitely
            avail_end = end

        # Check if availability period overlaps with query range
        if avail_end <= start or avail_start >= end:
            continue

        # Clip to query range
        period_start = max(avail_start, start)
        period_end = min(avail_end, end)

        # Get the default busy type from BUSYTYPE property
        busytype = vavail.get("BUSYTYPE", "BUSY-UNAVAILABLE")
        if isinstance(busytype, str):
            pass  # Already a string
        else:
            # It's an iCalendar property value
            busytype = str(busytype)

        # Add this busy period to timeline (may override lower priority periods)
        _add_period_to_timeline(timeline, period_start, period_end, busytype, priority)

        # Process AVAILABLE subcomponents to mark free time
        for subcomp in vavail.subcomponents:
            if subcomp.name == "AVAILABLE":
                sub_dtstart = subcomp.get("DTSTART")
                sub_dtend = subcomp.get("DTEND")
                sub_duration = subcomp.get("DURATION")

                if not sub_dtstart:
                    continue

                sub_start = tzify(sub_dtstart.dt)

                if sub_dtend:
                    sub_end = tzify(sub_dtend.dt)
                elif sub_duration:
                    sub_end = sub_start + sub_duration.dt
                else:
                    # No end time for AVAILABLE period
                    continue

                # Check if AVAILABLE period overlaps with query range and availability range
                if sub_end <= max(period_start, start) or sub_start >= min(
                    period_end, end
                ):
                    continue

                # Clip to both query range and availability range
                free_start = max(sub_start, period_start, start)
                free_end = min(sub_end, period_end, end)

                # Mark this period as free (same priority as parent VAVAILABILITY)
                _add_period_to_timeline(
                    timeline, free_start, free_end, "FREE", priority
                )

    # Convert timeline to final periods
    return _timeline_to_periods(timeline)


def _add_period_to_timeline(timeline, start, end, fbtype, priority):
    """Add a period to the timeline, handling overlaps based on priority.

    Higher priority periods override lower priority ones.
    For same priority, busy types are ordered: BUSY > BUSY-UNAVAILABLE > BUSY-TENTATIVE > FREE
    """
    # Busy type precedence for same priority
    fbtype_precedence = {
        "BUSY": 4,
        "BUSY-UNAVAILABLE": 3,
        "BUSY-TENTATIVE": 2,
        "FREE": 1,
    }

    if not timeline:
        timeline.append((start, end, fbtype, priority))
        return

    new_timeline = []
    current_start = start
    current_end = end

    for p_start, p_end, p_fbtype, p_priority in timeline:
        # No overlap with current period
        if p_end <= current_start or p_start >= current_end:
            new_timeline.append((p_start, p_end, p_fbtype, p_priority))
            continue

        # There is overlap - determine which takes precedence
        # Special case: FREE periods from AVAILABLE always override busy periods at same priority
        if priority == p_priority and fbtype == "FREE" and p_fbtype != "FREE":
            new_has_precedence = True
        else:
            new_has_precedence = priority < p_priority or (
                priority == p_priority
                and fbtype_precedence.get(fbtype, 0)
                > fbtype_precedence.get(p_fbtype, 0)
            )

        if new_has_precedence:
            # New period takes precedence in overlap region
            # Keep non-overlapping parts of existing period
            if p_start < current_start:
                new_timeline.append((p_start, current_start, p_fbtype, p_priority))
            if p_end > current_end:
                new_timeline.append((current_end, p_end, p_fbtype, p_priority))
        else:
            # Existing period takes precedence
            # Add the existing period
            new_timeline.append((p_start, p_end, p_fbtype, p_priority))

            # Adjust current period to exclude overlap
            if p_start <= current_start < p_end <= current_end:
                # Existing covers start of new period
                current_start = p_end
            elif current_start < p_start < current_end <= p_end:
                # Existing covers end of new period
                current_end = p_start
            elif p_start <= current_start and p_end >= current_end:
                # Existing completely covers new period
                current_start = current_end  # Mark as consumed
            elif current_start < p_start and p_end < current_end:
                # Existing is in middle of new period - split needed
                # Add first part of new period
                new_timeline.append((current_start, p_start, fbtype, priority))
                current_start = p_end  # Continue with remainder

    # Add any remaining part of the new period
    if current_start < current_end:
        new_timeline.append((current_start, current_end, fbtype, priority))

    # Sort by start time
    timeline.clear()
    timeline.extend(sorted(new_timeline, key=lambda x: x[0]))


def _timeline_to_periods(timeline):
    """Convert timeline to final periods, merging adjacent periods with same fbtype."""
    if not timeline:
        return []

    periods = []
    current_start, current_end, current_fbtype, _ = timeline[0]

    for start, end, fbtype, _ in timeline[1:]:
        if start == current_end and fbtype == current_fbtype:
            # Extend current period
            current_end = end
        else:
            # Save current period and start new one
            if current_fbtype != "FREE":  # Don't return FREE periods
                periods.append((current_start, current_end, current_fbtype))
            current_start, current_end, current_fbtype = start, end, fbtype

    # Save last period
    if current_fbtype != "FREE":
        periods.append((current_start, current_end, current_fbtype))

    return periods


async def iter_freebusy(resources, start, end, tzify):
    # Collect all VAVAILABILITY components first for priority-based processing
    vavailability_components = []
    event_periods = []

    async for href, resource in resources:
        # For free/busy queries, expand recurring events within the query range
        c = await calendar_from_resource(resource, start, end)
        if c is None:
            continue
        if c.name != "VCALENDAR":
            continue
        for comp in c.subcomponents:
            if comp.name == "VEVENT":
                if apply_time_range_vevent(start, end, comp, tzify):
                    vp = extract_freebusy(comp, tzify)
                    if vp is not None:
                        event_periods.append(vp)
            elif comp.name == "VAVAILABILITY":
                # Collect VAVAILABILITY components for priority-based processing
                if apply_time_range_vavailability(start, end, comp, tzify):
                    vavailability_components.append(comp)

    # Process VAVAILABILITY components according to RFC 7953 priority rules
    if vavailability_components:
        availability_periods = process_vavailability_components(
            vavailability_components, start, end, tzify
        )

        # Convert availability periods to vPeriod objects
        for period_start, period_end, fbtype in availability_periods:
            period = vPeriod((period_start, period_end))
            if fbtype != "BUSY":
                period.params["FBTYPE"] = fbtype
            yield period

    # Yield event periods (these override availability)
    for period in event_periods:
        yield period


class FreeBusyQueryReporter(webdav.Reporter):
    """free-busy-query reporter.

    See https://tools.ietf.org/html/rfc4791, section 7.10
    """

    name = "{urn:ietf:params:xml:ns:caldav}free-busy-query"
    resource_type = CALENDAR_RESOURCE_TYPE

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
        for el in body:
            if el.tag == "{urn:ietf:params:xml:ns:caldav}time-range":
                requested = el
            else:
                webdav.nonfatal_bad_request("unexpected XML element", strict)
                continue
        tz = get_calendar_timezone(base_resource)

        def tzify(dt):
            return as_tz_aware_ts(dt, tz).astimezone(ZoneInfo("UTC"))

        (start, end) = _parse_time_range(requested)
        ret = ICalendar()
        ret["VERSION"] = "2.0"
        ret["PRODID"] = PRODID
        fb = FreeBusy()
        fb["DTSTAMP"] = vDDDTypes(tzify(datetime.datetime.now()))
        fb["DTSTART"] = vDDDTypes(start)
        fb["DTEND"] = vDDDTypes(end)
        fb["FREEBUSY"] = [
            item
            async for item in iter_freebusy(
                webdav.traverse_resource(base_resource, base_href, depth),
                start,
                end,
                tzify,
            )
        ]
        ret.add_component(fb)
        return webdav.Response(status="200 OK", body=[ret.to_ical()])


class MkcalendarMethod(webdav.Method):
    async def handle(self, request, environ, app):
        content_type = request.content_type
        base_content_type, params = webdav.parse_type(content_type)
        if base_content_type not in (
            "text/xml",
            "application/xml",
            None,
            "text/plain",
            "application/octet-stream",
        ):
            raise webdav.UnsupportedMediaType(content_type)
        href, path, resource = app._get_resource_from_environ(request, environ)
        if resource is not None:
            return webdav._send_simple_dav_error(
                request,
                "403 Forbidden",
                error=ET.Element("{DAV:}resource-must-be-null"),
                description=f"Something already exists at {path!r}",
            )
        try:
            resource = app.backend.create_collection(path)
        except FileNotFoundError:
            return webdav.Response(status="409 Conflict")
        el = ET.Element("{DAV:}resourcetype")
        await app.properties["{DAV:}resourcetype"].get_value(
            href, resource, el, environ
        )
        ET.SubElement(el, "{urn:ietf:params:xml:ns:caldav}calendar")
        await app.properties["{DAV:}resourcetype"].set_value(href, resource, el)
        if base_content_type in ("text/xml", "application/xml"):
            et = await webdav._readXmlBody(
                request,
                "{urn:ietf:params:xml:ns:caldav}mkcalendar",
                strict=app.strict,
            )
            propstat = []
            for el in et:
                if el.tag != "{DAV:}set":
                    webdav.nonfatal_bad_request(
                        f"Unknown tag {el.tag} in mkcalendar", app.strict
                    )
                    continue
                propstat.extend(
                    [
                        ps
                        async for ps in webdav.apply_modify_prop(
                            el, href, resource, app.properties
                        )
                    ]
                )
                ret = ET.Element("{urn:ietf:params:xml:ns:carldav:}mkcalendar-response")
            for propstat_el in webdav.propstat_as_xml(propstat):
                ret.append(propstat_el)
            return webdav._send_xml_response(
                "201 Created", ret, webdav.DEFAULT_ENCODING
            )
        else:
            return webdav.Response(status="201 Created")
