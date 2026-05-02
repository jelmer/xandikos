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

"""Scheduling.

See https://tools.ietf.org/html/rfc6638
"""

import hashlib

from icalendar.cal import Calendar

from xandikos import caldav, webdav
from xandikos.caldav import (
    SCHEDULE_INBOX_RESOURCE_TYPE,
    SCHEDULE_OUTBOX_RESOURCE_TYPE,
)
from xandikos.icalendar import PropTypes

# Feature to advertise to indicate scheduling support.
FEATURE = "calendar-auto-schedule"

CALENDAR_USER_TYPE_INDIVIDUAL = "INDIVIDUAL"  # An individual
CALENDAR_USER_TYPE_GROUP = "GROUP"  # A group of individuals
CALENDAR_USER_TYPE_RESOURCE = "RESOURCE"  # A physical resource
CALENDAR_USER_TYPE_ROOM = "ROOM"  # A room resource
CALENDAR_USER_TYPE_UNKNOWN = "UNKNOWN"  # Otherwise not known

CALENDAR_USER_TYPES = (
    CALENDAR_USER_TYPE_INDIVIDUAL,
    CALENDAR_USER_TYPE_GROUP,
    CALENDAR_USER_TYPE_RESOURCE,
    CALENDAR_USER_TYPE_ROOM,
    CALENDAR_USER_TYPE_UNKNOWN,
)


# Properties whose values participate in iTIP scheduling. The schedule-tag
# (RFC 6638 §3.2.10) only changes when one of these changes within a
# scheduling-bearing component; bookkeeping properties such as DTSTAMP,
# LAST-MODIFIED, and CREATED do not affect it.
SCHEDULING_PROPERTIES = frozenset(
    {
        "ATTENDEE",
        "ORGANIZER",
        "DTSTART",
        "DTEND",
        "DUE",
        "DURATION",
        "RRULE",
        "RDATE",
        "EXDATE",
        "RECURRENCE-ID",
        "SEQUENCE",
        "STATUS",
        "SUMMARY",
        "LOCATION",
        "DESCRIPTION",
        "PRIORITY",
        "TRANSP",
        "CLASS",
        "URL",
        "CATEGORIES",
        "RESOURCES",
        "PERCENT-COMPLETE",
        "REQUEST-STATUS",
    }
)


# Components that carry scheduling state. Other component types (VTIMEZONE,
# VALARM, VFREEBUSY responses inside replies, etc.) are intentionally skipped
# so they do not destabilise the tag.
SCHEDULING_COMPONENTS = frozenset({"VEVENT", "VTODO", "VJOURNAL"})


def _serialize_scheduling_value(value: PropTypes) -> bytes:
    """Serialise a single iCalendar property value, including its parameters.

    Plain ``to_ical()`` would drop parameters such as ``PARTSTAT`` on
    ATTENDEE, which is exactly the kind of state the schedule-tag must
    track. We fold params and value into one sorted, opaque byte string.
    """
    rendered = value.to_ical()
    if value.params:
        # Parameter names are case-insensitive; normalise to upper for stability.
        param_items = sorted(
            (k.upper().encode("ascii"), str(v).encode("utf-8"))
            for k, v in value.params.items()
        )
        rendered = b";".join(b"=".join(item) for item in param_items) + b":" + rendered
    return rendered


def extract_scheduling_signature(cal: Calendar) -> bytes:
    """Compute a stable signature of the scheduling-relevant content in *cal*.

    Two calendars with the same signature are considered equivalent for the
    purposes of CalDAV scheduling: a PUT that only changes properties outside
    SCHEDULING_PROPERTIES (or properties on non-scheduling components) yields
    the same signature, and therefore the same schedule-tag.

    Args:
      cal: parsed icalendar Calendar object.

    Returns: opaque ``bytes`` value suitable for hashing or direct comparison.
    """
    components: list[tuple[bytes, list[tuple[bytes, list[bytes]]]]] = []
    for component in cal.subcomponents:
        if component.name is None:
            continue
        name = component.name.upper()
        if name not in SCHEDULING_COMPONENTS:
            continue
        try:
            uid = component["UID"].to_ical()
        except KeyError:
            uid = b""
        try:
            recurrence_id = component["RECURRENCE-ID"].to_ical()
        except KeyError:
            recurrence_id = b""
        props: list[tuple[bytes, list[bytes]]] = []
        for field in component:
            if field.upper() not in SCHEDULING_PROPERTIES:
                continue
            value = component.get(field)
            if value is None:
                continue
            if isinstance(value, list):
                items = [_serialize_scheduling_value(v) for v in value]
            else:
                items = [_serialize_scheduling_value(value)]
            items.sort()
            props.append((field.upper().encode("ascii"), items))
        props.sort()
        components.append(
            (name.encode("ascii") + b":" + uid + b":" + recurrence_id, props)
        )
    components.sort()

    h = hashlib.sha256()
    for comp_key, props in components:
        h.update(b"C\x00")
        h.update(comp_key)
        h.update(b"\x00")
        for field_name, items in props:
            h.update(b"P\x00")
            h.update(field_name)
            h.update(b"\x00")
            for item in items:
                h.update(b"V\x00")
                h.update(item)
                h.update(b"\x00")
    return h.digest()


class ScheduleInbox(webdav.Collection):
    resource_types = webdav.Collection.resource_types + [SCHEDULE_INBOX_RESOURCE_TYPE]

    def get_calendar_user_type(self):
        # Default, per section 2.4.2
        return CALENDAR_USER_TYPE_INDIVIDUAL

    def get_calendar_timezone(self):
        """Return calendar timezone.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.get_calendar_timezone)

    def set_calendar_timezone(self):
        """Set calendar timezone.

        This should be an iCalendar object with exactly one
        VTIMEZONE component.
        """
        raise NotImplementedError(self.set_calendar_timezone)

    def get_supported_calendar_components(self):
        """Return set of supported calendar components in this calendar.

        Returns: iterable over component names
        """
        raise NotImplementedError(self.get_supported_calendar_components)

    def get_supported_calendar_data_types(self):
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

    def get_schedule_default_calendar_url(self):
        """Return default calendar URL.

        None indicates there is no default URL.
        """
        return None


class ScheduleOutbox(webdav.Collection):
    resource_types = webdav.Collection.resource_types + [SCHEDULE_OUTBOX_RESOURCE_TYPE]

    def get_supported_calendar_components(self):
        """Return set of supported calendar components in this calendar.

        Returns: iterable over component names
        """
        raise NotImplementedError(self.get_supported_calendar_components)

    def get_supported_calendar_data_types(self):
        """Return supported calendar data types.

        Returns: iterable over (content_type, version) tuples
        """
        raise NotImplementedError(self.get_supported_calendar_data_types)

    def get_max_resource_size(self):
        """Return max resource size."""
        raise NotImplementedError(self.get_max_resource_size)

    def get_min_date_time(self):
        """Return minimum datetime property."""
        raise NotImplementedError(self.get_min_date_time)

    def get_max_date_time(self):
        """Return maximum datetime property."""
        raise NotImplementedError(self.get_max_date_time)

    def get_max_attendees_per_instance(self):
        """Return maximum number of attendees per instance."""
        raise NotImplementedError(self.get_max_attendees_per_instance)


class ScheduleInboxURLProperty(webdav.Property):
    """Schedule-inbox-URL property.

    See https://tools.ietf.org/html/rfc6638, section 2.2
    """

    name = "{%s}schedule-inbox-URL" % caldav.NAMESPACE
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = True

    async def get_value(self, href, resource, el, environ):
        el.append(webdav.create_href(resource.get_schedule_inbox_url(), href))


class ScheduleOutboxURLProperty(webdav.Property):
    """Schedule-outbox-URL property.

    See https://tools.ietf.org/html/rfc6638, section 2.1
    """

    name = "{%s}schedule-outbox-URL" % caldav.NAMESPACE
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = True

    async def get_value(self, href, resource, el, environ):
        el.append(webdav.create_href(resource.get_schedule_outbox_url(), href))


class CalendarUserAddressSetProperty(webdav.Property):
    """calendar-user-address-set property.

    See https://tools.ietf.org/html/rfc6638, section 2.4.1
    """

    name = "{%s}calendar-user-address-set" % caldav.NAMESPACE
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False

    async def get_value(self, base_href, resource, el, environ):
        for href in resource.get_calendar_user_address_set():
            el.append(webdav.create_href(href, base_href))


class ScheduleTagProperty(webdav.Property):
    """schedule-tag property.

    See https://tools.ietf.org/html/rfc6638, section 3.2.10
    """

    name = "{%s}schedule-tag" % caldav.NAMESPACE
    in_allprops = False

    def supported_on(self, resource):
        return resource.get_content_type() == "text/calendar"

    async def get_value(self, base_href, resource, el, environ):
        el.text = resource.get_schedule_tag()


class CalendarUserTypeProperty(webdav.Property):
    """calendar-user-type property.

    See https://tools.ietf.org/html/rfc6638, section 2.4.2
    """

    name = "{%s}calendar-user-type" % caldav.NAMESPACE
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_calendar_user_type()


class ScheduleDefaultCalendarURLProperty(webdav.Property):
    """schedule-default-calendar-URL property.

    See https://tools.ietf.org/html/rfc6638, section-9.2
    """

    name = "{%s}schedule-default-calendar-URL" % caldav.NAMESPACE
    resource_type = SCHEDULE_INBOX_RESOURCE_TYPE
    in_allprops = True

    async def get_value(self, href, resource, el, environ):
        url = resource.get_schedule_default_calendar_url()
        if url is not None:
            el.append(webdav.create_href(url, href))
