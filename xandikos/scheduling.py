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
import posixpath
from collections.abc import Iterable
from xml.etree import ElementTree as ET

from icalendar.cal import Calendar
from icalendar.prop import vPeriod

from xandikos import caldav, itip, webdav
from xandikos.caldav import (
    SCHEDULE_INBOX_RESOURCE_TYPE,
    SCHEDULE_OUTBOX_RESOURCE_TYPE,
)
from xandikos.itip import (
    REQUEST_STATUS_NO_AUTHORITY,
    REQUEST_STATUS_SUCCESS,
    InvalidSchedulingRequest,
)


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
            request_comp = itip.validate_freebusy_request(cal)
        except InvalidSchedulingRequest as exc:
            raise webdav.BadRequestError(exc.description) from exc

        start, end = itip.parse_freebusy_window(request_comp)

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
            reply = itip.build_freebusy_reply(
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
