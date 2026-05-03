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

import datetime
import hashlib
import posixpath
from collections.abc import Iterable
from xml.etree import ElementTree as ET

from icalendar.cal import Calendar, Component, FreeBusy
from icalendar.prop import vDDDTypes, vPeriod

from xandikos import caldav, webdav
from xandikos.caldav import (
    PRODID,
    SCHEDULE_INBOX_RESOURCE_TYPE,
    SCHEDULE_OUTBOX_RESOURCE_TYPE,
)
from xandikos.icalendar import PropTypes


# RFC 5546 §3.6 / RFC 6638 §6.2 request-status codes used in
# schedule-response replies.
REQUEST_STATUS_SUCCESS = "2.0;Success"
REQUEST_STATUS_INVALID_CALENDAR_USER = "3.7;Invalid calendar user"
REQUEST_STATUS_NO_AUTHORITY = "3.8;No authority"
REQUEST_STATUS_SERVICE_UNAVAILABLE = "5.0;Service unavailable"


def build_itip_cancel(cal: Component) -> Calendar:
    """Build a METHOD:CANCEL VCALENDAR for *cal*.

    Per RFC 5546 §3.2.5, an iTIP CANCEL re-sends the scheduling
    components from the original event, with SEQUENCE bumped by one,
    DTSTAMP set to "now", and STATUS:CANCELLED on each component.
    Non-scheduling components (VTIMEZONE, etc.) are passed through.
    """
    out = Calendar()
    out["VERSION"] = "2.0"
    out["PRODID"] = PRODID
    out["METHOD"] = "CANCEL"
    now = datetime.datetime.now(datetime.timezone.utc)
    for comp in cal.subcomponents:
        clone = comp.copy()
        if clone.name in SCHEDULING_COMPONENTS:
            clone["DTSTAMP"] = vDDDTypes(now)
            try:
                seq = int(comp.get("SEQUENCE", 0))
            except (TypeError, ValueError):
                seq = 0
            clone["SEQUENCE"] = seq + 1
            clone["STATUS"] = "CANCELLED"
        out.add_component(clone)
    return out


async def deliver_itip_to_inbox(
    backend: "webdav.Backend",
    attendee_address: str,
    itip_message: Calendar,
    name_hint: str | None = None,
) -> bool:
    """Deliver *itip_message* to *attendee_address*'s schedule-inbox.

    Returns ``True`` on successful delivery, ``False`` if the address
    doesn't belong to a local principal (caller's cue to fall back to
    iMIP or skip). Raises whatever the inbox collection's
    ``create_member`` raises on storage failure.
    """
    found = find_principal_by_calendar_user_address(backend, attendee_address)
    if found is None:
        return False
    principal_path, principal = found
    inbox_path = posixpath.join(principal_path, principal.get_schedule_inbox_url())
    inbox = backend.get_resource(inbox_path)
    if inbox is None or not isinstance(inbox, webdav.Collection):
        return False
    body = itip_message.to_ical()
    await inbox.create_member(name_hint, [body], "text/calendar")
    return True


def find_owning_principal(
    backend: "webdav.Backend", relpath: str
) -> "tuple[str, webdav.Principal] | None":
    """Walk up *relpath* until a principal is found, or return None.

    Useful for collections that need to find the principal they belong
    to without baking in a specific directory layout (e.g. a calendar
    collection at ``/alice/calendars/work`` finds the principal at
    ``/alice``).
    """
    p = relpath.rstrip("/") or "/"
    while True:
        principal = backend.get_principal(p)
        if principal is not None:
            return p, principal
        if p in ("/", ""):
            return None
        p = posixpath.dirname(p) or "/"


def find_principal_by_calendar_user_address(
    backend: "webdav.Backend", address: str
) -> "tuple[str, webdav.Principal] | None":
    """Look up the local principal owning *address*, or None.

    Walks ``backend.find_principals()`` and matches *address* (typically
    a ``mailto:`` URI) against each principal's
    ``calendar-user-address-set``. Returns ``(relpath, principal)`` so
    the caller can resolve the principal's collections (inbox,
    calendar-home, …) via ``backend.get_resource``.

    Used to route iTIP messages to local inboxes; addresses that don't
    match any local principal are considered remote and the caller can
    fall back to iMIP (or skip).
    """
    for path in backend.find_principals():
        principal = backend.get_principal(path)
        if principal is None:
            continue
        if address in principal.get_calendar_user_address_set():
            return path, principal
    return None


class InvalidSchedulingRequest(Exception):
    """The body submitted to the schedule-outbox is not a valid request."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


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

    async def get_attendee_busy_periods(
        self,
        attendee_address: str,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> Iterable[vPeriod] | None:
        """Look up busy periods for *attendee_address* over [start, end).

        Returns ``None`` if the server has no authority to answer for the
        given attendee — that is the cue to emit a 3.7/3.8 status in the
        schedule-response. The default implementation returns ``None`` for
        all attendees; concrete servers override this to walk the
        principal's calendar collections (or query a remote server).
        """
        return None

    async def handle_post(
        self,
        request,
        environ,
        path: str,
        body: list[bytes],
        content_type: str,
    ) -> "webdav.Response":
        """Handle a POST to the schedule-outbox per RFC 6638 §6."""
        if content_type != "text/calendar":
            return webdav.Response(
                status=415,
                reason="Unsupported Media Type",
                body=[b"Expected text/calendar"],
            )
        raw = b"".join(body).decode("utf-8")
        try:
            cal = Calendar.from_ical(raw)
        except ValueError as exc:
            raise webdav.BadRequestError(f"Invalid iCalendar: {exc}") from exc
        try:
            request_comp = _validate_freebusy_request(cal)
        except InvalidSchedulingRequest as exc:
            raise webdav.BadRequestError(exc.description) from exc

        start, end = _parse_freebusy_window(request_comp)

        organizer = request_comp.get("ORGANIZER")
        attendees = request_comp.get("ATTENDEE", [])
        if not isinstance(attendees, list):
            attendees = [attendees]

        responses: list[ET.Element] = []
        for attendee in attendees:
            recipient = str(attendee)
            periods = await self.get_attendee_busy_periods(recipient, start, end)
            if periods is None:
                responses.append(
                    _build_response_element(
                        recipient, REQUEST_STATUS_NO_AUTHORITY, None
                    )
                )
                continue
            reply = _build_freebusy_reply(
                organizer, recipient, request_comp, start, end, list(periods)
            )
            responses.append(
                _build_response_element(
                    recipient, REQUEST_STATUS_SUCCESS, reply.to_ical()
                )
            )

        root = ET.Element("{%s}schedule-response" % caldav.NAMESPACE)
        for r in responses:
            root.append(r)
        body_bytes = ET.tostring(root, encoding="utf-8")
        return webdav.Response(
            status=200,
            reason="OK",
            body=[body_bytes],
            headers={"Content-Type": "application/xml; charset=utf-8"},
        )


def _validate_freebusy_request(cal: Component) -> Component:
    """Return the single VFREEBUSY in *cal* if the request is well formed."""
    method = cal.get("METHOD")
    if str(method).upper() != "REQUEST":
        raise InvalidSchedulingRequest(
            "Schedule-outbox requests require METHOD:REQUEST"
        )
    fbs = [c for c in cal.subcomponents if c.name == "VFREEBUSY"]
    others = [
        c.name for c in cal.subcomponents if c.name not in ("VFREEBUSY", "VTIMEZONE")
    ]
    if others:
        raise InvalidSchedulingRequest(
            f"Free-busy request must contain only VFREEBUSY, got {others!r}"
        )
    if len(fbs) != 1:
        raise InvalidSchedulingRequest(
            f"Free-busy request must contain exactly one VFREEBUSY, got {len(fbs)}"
        )
    fb = fbs[0]
    if "ORGANIZER" not in fb:
        raise InvalidSchedulingRequest("VFREEBUSY missing ORGANIZER")
    if "ATTENDEE" not in fb:
        raise InvalidSchedulingRequest("VFREEBUSY missing ATTENDEE")
    if "DTSTART" not in fb or "DTEND" not in fb:
        raise InvalidSchedulingRequest("VFREEBUSY missing DTSTART/DTEND")
    return fb


def _parse_freebusy_window(
    fb: Component,
) -> tuple[datetime.datetime, datetime.datetime]:
    start = fb["DTSTART"].dt
    end = fb["DTEND"].dt
    if isinstance(start, datetime.date) and not isinstance(start, datetime.datetime):
        start = datetime.datetime.combine(start, datetime.time(), datetime.timezone.utc)
    if isinstance(end, datetime.date) and not isinstance(end, datetime.datetime):
        end = datetime.datetime.combine(end, datetime.time(), datetime.timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=datetime.timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=datetime.timezone.utc)
    return start, end


def _build_freebusy_reply(
    organizer,
    recipient: str,
    request_comp: Component,
    start: datetime.datetime,
    end: datetime.datetime,
    periods: list[vPeriod],
) -> Calendar:
    """Build a METHOD:REPLY VCALENDAR with the per-recipient VFREEBUSY."""
    cal = Calendar()
    cal["VERSION"] = "2.0"
    cal["PRODID"] = PRODID
    cal["METHOD"] = "REPLY"
    fb = FreeBusy()
    fb["DTSTAMP"] = vDDDTypes(datetime.datetime.now(datetime.timezone.utc))
    fb["DTSTART"] = vDDDTypes(start)
    fb["DTEND"] = vDDDTypes(end)
    if organizer is not None:
        fb["ORGANIZER"] = organizer
    fb["ATTENDEE"] = recipient
    if "UID" in request_comp:
        fb["UID"] = request_comp["UID"]
    if periods:
        fb["FREEBUSY"] = periods
    cal.add_component(fb)
    return cal


def _build_response_element(
    recipient: str, request_status: str, calendar_data: bytes | None
) -> ET.Element:
    el = ET.Element("{%s}response" % caldav.NAMESPACE)
    rec = ET.SubElement(el, "{%s}recipient" % caldav.NAMESPACE)
    rec.append(webdav.create_href(recipient))
    status = ET.SubElement(el, "{%s}request-status" % caldav.NAMESPACE)
    status.text = request_status
    if calendar_data is not None:
        cd = ET.SubElement(el, "{%s}calendar-data" % caldav.NAMESPACE)
        cd.text = calendar_data.decode("utf-8")
    return el


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
        el.text = await resource.get_schedule_tag()


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
