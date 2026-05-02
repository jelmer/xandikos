# Xandikos
# Copyright (C) 2025 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Tests for xandikos.scheduling (RFC 6638 CalDAV Scheduling)."""

import asyncio
import hashlib
import unittest

from icalendar.cal import Calendar

from xandikos import scheduling, webdav
from xandikos.webdav import ET


class ScheduleInboxURLPropertyTests(unittest.TestCase):
    """Tests for ScheduleInboxURLProperty (RFC 6638 Section 2.2)."""

    def test_property_name(self):
        """Test schedule-inbox-URL property name."""
        prop = scheduling.ScheduleInboxURLProperty()
        self.assertEqual(prop.name, "{urn:ietf:params:xml:ns:caldav}schedule-inbox-URL")

    def test_property_attributes(self):
        """Test schedule-inbox-URL property attributes.

        RFC 6638 Section 2.2: Identifies the URL of the scheduling
        inbox collection for the principal.
        """
        prop = scheduling.ScheduleInboxURLProperty()
        self.assertTrue(prop.in_allprops)
        self.assertEqual(prop.resource_type, webdav.PRINCIPAL_RESOURCE_TYPE)

    def test_get_value(self):
        """Test schedule-inbox-URL property value.

        RFC 6638 Section 2.2: The property contains a single DAV:href
        element pointing to the scheduling inbox URL.
        """

        async def run_test():
            prop = scheduling.ScheduleInboxURLProperty()

            class MockResource:
                def get_schedule_inbox_url(self):
                    return "/calendars/user1/inbox/"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/calendars/user1/inbox/")

        asyncio.run(run_test())

    def test_get_value_relative_url(self):
        """Test schedule-inbox-URL with relative URL resolution."""

        async def run_test():
            prop = scheduling.ScheduleInboxURLProperty()

            class MockResource:
                def get_schedule_inbox_url(self):
                    return "inbox/"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            # Should be resolved relative to base href
            self.assertEqual(hrefs[0].text, "/principals/user1/inbox/")

        asyncio.run(run_test())


class ScheduleOutboxURLPropertyTests(unittest.TestCase):
    """Tests for ScheduleOutboxURLProperty (RFC 6638 Section 2.1)."""

    def test_property_name(self):
        """Test schedule-outbox-URL property name."""
        prop = scheduling.ScheduleOutboxURLProperty()
        self.assertEqual(
            prop.name, "{urn:ietf:params:xml:ns:caldav}schedule-outbox-URL"
        )

    def test_property_attributes(self):
        """Test schedule-outbox-URL property attributes.

        RFC 6638 Section 2.1: Identifies the URL of the scheduling
        outbox collection for the principal.
        """
        prop = scheduling.ScheduleOutboxURLProperty()
        self.assertTrue(prop.in_allprops)
        self.assertEqual(prop.resource_type, webdav.PRINCIPAL_RESOURCE_TYPE)

    def test_get_value(self):
        """Test schedule-outbox-URL property value.

        RFC 6638 Section 2.1: The property contains a single DAV:href
        element pointing to the scheduling outbox URL.
        """

        async def run_test():
            prop = scheduling.ScheduleOutboxURLProperty()

            class MockResource:
                def get_schedule_outbox_url(self):
                    return "/calendars/user1/outbox/"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/calendars/user1/outbox/")

        asyncio.run(run_test())


class CalendarUserAddressSetPropertyTests(unittest.TestCase):
    """Tests for CalendarUserAddressSetProperty (RFC 6638 Section 2.4.1)."""

    def test_property_name(self):
        """Test calendar-user-address-set property name."""
        prop = scheduling.CalendarUserAddressSetProperty()
        self.assertEqual(
            prop.name, "{urn:ietf:params:xml:ns:caldav}calendar-user-address-set"
        )

    def test_property_attributes(self):
        """Test calendar-user-address-set property attributes.

        RFC 6638 Section 2.4.1: Identifies calendar user addresses
        that correspond to this principal.
        """
        prop = scheduling.CalendarUserAddressSetProperty()
        self.assertFalse(prop.in_allprops)
        self.assertEqual(prop.resource_type, webdav.PRINCIPAL_RESOURCE_TYPE)

    def test_get_value_single_address(self):
        """Test calendar-user-address-set with single address.

        RFC 6638 Section 2.4.1: Contains one or more DAV:href elements
        with calendar user addresses (typically mailto: URIs).
        """

        async def run_test():
            prop = scheduling.CalendarUserAddressSetProperty()

            class MockResource:
                def get_calendar_user_address_set(self):
                    return ["mailto:user1@example.com"]

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            # mailto URIs are URL-encoded by create_href
            self.assertEqual(hrefs[0].text, "mailto%3Auser1%40example.com")

        asyncio.run(run_test())

    def test_get_value_multiple_addresses(self):
        """Test calendar-user-address-set with multiple addresses.

        RFC 6638 Section 2.4.1: A principal can have multiple
        calendar user addresses.
        """

        async def run_test():
            prop = scheduling.CalendarUserAddressSetProperty()

            class MockResource:
                def get_calendar_user_address_set(self):
                    return [
                        "mailto:user1@example.com",
                        "mailto:user1@otherdomain.com",
                        "/principals/user1/",
                    ]

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 3)
            # Check exact values in order - mailto URIs are URL-encoded by create_href
            self.assertEqual(hrefs[0].text, "mailto%3Auser1%40example.com")
            self.assertEqual(hrefs[1].text, "mailto%3Auser1%40otherdomain.com")
            self.assertEqual(hrefs[2].text, "/principals/user1/")

        asyncio.run(run_test())

    def test_get_value_empty_set(self):
        """Test calendar-user-address-set with no addresses."""

        async def run_test():
            prop = scheduling.CalendarUserAddressSetProperty()

            class MockResource:
                def get_calendar_user_address_set(self):
                    return []

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 0)

        asyncio.run(run_test())


class ScheduleTagPropertyTests(unittest.TestCase):
    """Tests for ScheduleTagProperty (RFC 6638 Section 3.2.10)."""

    def test_property_name(self):
        """Test schedule-tag property name."""
        prop = scheduling.ScheduleTagProperty()
        self.assertEqual(prop.name, "{urn:ietf:params:xml:ns:caldav}schedule-tag")

    def test_property_attributes(self):
        """Test schedule-tag property attributes.

        RFC 6638 Section 3.2.10: The schedule-tag property provides
        an entity tag for scheduling object resources.
        """
        prop = scheduling.ScheduleTagProperty()
        self.assertFalse(prop.in_allprops)
        self.assertIsNone(prop.resource_type)

    def test_supported_on_calendar(self):
        """Test that schedule-tag is supported on calendar resources."""
        prop = scheduling.ScheduleTagProperty()

        class CalendarResource:
            def get_content_type(self):
                return "text/calendar"

        self.assertTrue(prop.supported_on(CalendarResource()))

    def test_supported_on_non_calendar(self):
        """Test that schedule-tag is not supported on non-calendar resources."""
        prop = scheduling.ScheduleTagProperty()

        class NonCalendarResource:
            def get_content_type(self):
                return "text/plain"

        self.assertFalse(prop.supported_on(NonCalendarResource()))

    def test_get_value(self):
        """Test schedule-tag property value.

        RFC 6638 Section 3.2.10: The property contains an opaque
        string that changes whenever scheduling-relevant changes occur.
        """

        async def run_test():
            prop = scheduling.ScheduleTagProperty()

            class MockResource:
                def get_content_type(self):
                    return "text/calendar"

                async def get_schedule_tag(self):
                    return "schedule-tag-12345"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/event.ics", resource, el, {})

            self.assertEqual(el.text, "schedule-tag-12345")

        asyncio.run(run_test())


class CalendarUserTypePropertyTests(unittest.TestCase):
    """Tests for CalendarUserTypeProperty (RFC 6638 Section 2.4.2)."""

    def test_property_name(self):
        """Test calendar-user-type property name."""
        prop = scheduling.CalendarUserTypeProperty()
        self.assertEqual(prop.name, "{urn:ietf:params:xml:ns:caldav}calendar-user-type")

    def test_property_attributes(self):
        """Test calendar-user-type property attributes.

        RFC 6638 Section 2.4.2: Identifies the type of calendar user.
        """
        prop = scheduling.CalendarUserTypeProperty()
        self.assertFalse(prop.in_allprops)
        self.assertEqual(prop.resource_type, webdav.PRINCIPAL_RESOURCE_TYPE)

    def test_get_value_individual(self):
        """Test calendar-user-type for individual.

        RFC 6638 Section 2.4.2: INDIVIDUAL is the default type
        for a calendar user.
        """

        async def run_test():
            prop = scheduling.CalendarUserTypeProperty()

            class MockResource:
                def get_calendar_user_type(self):
                    return scheduling.CALENDAR_USER_TYPE_INDIVIDUAL

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            self.assertEqual(el.text, "INDIVIDUAL")

        asyncio.run(run_test())

    def test_get_value_group(self):
        """Test calendar-user-type for group."""

        async def run_test():
            prop = scheduling.CalendarUserTypeProperty()

            class MockResource:
                def get_calendar_user_type(self):
                    return scheduling.CALENDAR_USER_TYPE_GROUP

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/group1/", resource, el, {})

            self.assertEqual(el.text, "GROUP")

        asyncio.run(run_test())

    def test_get_value_resource(self):
        """Test calendar-user-type for resource."""

        async def run_test():
            prop = scheduling.CalendarUserTypeProperty()

            class MockResource:
                def get_calendar_user_type(self):
                    return scheduling.CALENDAR_USER_TYPE_RESOURCE

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/projector/", resource, el, {})

            self.assertEqual(el.text, "RESOURCE")

        asyncio.run(run_test())

    def test_get_value_room(self):
        """Test calendar-user-type for room."""

        async def run_test():
            prop = scheduling.CalendarUserTypeProperty()

            class MockResource:
                def get_calendar_user_type(self):
                    return scheduling.CALENDAR_USER_TYPE_ROOM

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/conference-room/", resource, el, {})

            self.assertEqual(el.text, "ROOM")

        asyncio.run(run_test())

    def test_get_value_unknown(self):
        """Test calendar-user-type for unknown type."""

        async def run_test():
            prop = scheduling.CalendarUserTypeProperty()

            class MockResource:
                def get_calendar_user_type(self):
                    return scheduling.CALENDAR_USER_TYPE_UNKNOWN

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/something/", resource, el, {})

            self.assertEqual(el.text, "UNKNOWN")

        asyncio.run(run_test())


class ScheduleDefaultCalendarURLPropertyTests(unittest.TestCase):
    """Tests for ScheduleDefaultCalendarURLProperty (RFC 6638 Section 9.2)."""

    def test_property_name(self):
        """Test schedule-default-calendar-URL property name."""
        prop = scheduling.ScheduleDefaultCalendarURLProperty()
        self.assertEqual(
            prop.name, "{urn:ietf:params:xml:ns:caldav}schedule-default-calendar-URL"
        )

    def test_property_attributes(self):
        """Test schedule-default-calendar-URL property attributes.

        RFC 6638 Section 9.2: Identifies the default calendar for
        scheduling operations.
        """
        prop = scheduling.ScheduleDefaultCalendarURLProperty()
        self.assertTrue(prop.in_allprops)
        self.assertEqual(prop.resource_type, scheduling.SCHEDULE_INBOX_RESOURCE_TYPE)

    def test_get_value_with_default(self):
        """Test schedule-default-calendar-URL with a default calendar.

        RFC 6638 Section 9.2: The property contains a single DAV:href
        element pointing to the default calendar.
        """

        async def run_test():
            prop = scheduling.ScheduleDefaultCalendarURLProperty()

            class MockResource:
                def get_schedule_default_calendar_url(self):
                    return "/calendars/user1/default/"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/inbox/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/calendars/user1/default/")

        asyncio.run(run_test())

    def test_get_value_without_default(self):
        """Test schedule-default-calendar-URL with no default calendar.

        RFC 6638 Section 9.2: The property may be absent or empty
        if no default calendar is set.
        """

        async def run_test():
            prop = scheduling.ScheduleDefaultCalendarURLProperty()

            class MockResource:
                def get_schedule_default_calendar_url(self):
                    return None

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/inbox/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 0)

        asyncio.run(run_test())


class ScheduleInboxTests(unittest.TestCase):
    """Tests for ScheduleInbox resource type."""

    def test_resource_types(self):
        """Test ScheduleInbox resource types.

        RFC 6638 Section 2.2: Schedule inbox collections MUST be
        identified by the CALDAV:schedule-inbox resourcetype.
        """
        inbox = scheduling.ScheduleInbox()
        self.assertIn(webdav.COLLECTION_RESOURCE_TYPE, inbox.resource_types)
        self.assertIn(scheduling.SCHEDULE_INBOX_RESOURCE_TYPE, inbox.resource_types)

    def test_get_calendar_user_type_default(self):
        """Test default calendar user type.

        RFC 6638 Section 2.4.2: The default calendar user type
        is INDIVIDUAL.
        """
        inbox = scheduling.ScheduleInbox()
        self.assertEqual(
            inbox.get_calendar_user_type(), scheduling.CALENDAR_USER_TYPE_INDIVIDUAL
        )

    def test_get_schedule_default_calendar_url_default(self):
        """Test default schedule calendar URL.

        The default implementation returns None when no default is set.
        """
        inbox = scheduling.ScheduleInbox()
        self.assertIsNone(inbox.get_schedule_default_calendar_url())


class ScheduleOutboxTests(unittest.TestCase):
    """Tests for ScheduleOutbox resource type."""

    def test_resource_types(self):
        """Test ScheduleOutbox resource types.

        RFC 6638 Section 2.1: Schedule outbox collections MUST be
        identified by the CALDAV:schedule-outbox resourcetype.
        """
        outbox = scheduling.ScheduleOutbox()
        self.assertIn(webdav.COLLECTION_RESOURCE_TYPE, outbox.resource_types)
        self.assertIn(scheduling.SCHEDULE_OUTBOX_RESOURCE_TYPE, outbox.resource_types)


class SchedulingConstantsTests(unittest.TestCase):
    """Tests for scheduling constants."""

    def test_calendar_user_types(self):
        """Test that all calendar user types are defined.

        RFC 6638 Section 2.4.2: Defines five calendar user types.
        """
        self.assertEqual(len(scheduling.CALENDAR_USER_TYPES), 5)
        self.assertIn("INDIVIDUAL", scheduling.CALENDAR_USER_TYPES)
        self.assertIn("GROUP", scheduling.CALENDAR_USER_TYPES)
        self.assertIn("RESOURCE", scheduling.CALENDAR_USER_TYPES)
        self.assertIn("ROOM", scheduling.CALENDAR_USER_TYPES)
        self.assertIn("UNKNOWN", scheduling.CALENDAR_USER_TYPES)

    def test_feature_constant(self):
        """Test scheduling feature constant.

        RFC 6638 Section 10.1: The feature identifier for
        calendar auto-scheduling.
        """
        self.assertEqual(scheduling.FEATURE, "calendar-auto-schedule")

    def test_resource_type_constants(self):
        """Test resource type constants are properly namespaced."""
        self.assertEqual(
            scheduling.SCHEDULE_INBOX_RESOURCE_TYPE,
            "{urn:ietf:params:xml:ns:caldav}schedule-inbox",
        )
        self.assertEqual(
            scheduling.SCHEDULE_OUTBOX_RESOURCE_TYPE,
            "{urn:ietf:params:xml:ns:caldav}schedule-outbox",
        )


class ExtractSchedulingSignatureTests(unittest.TestCase):
    """Tests for extract_scheduling_signature (RFC 6638 §3.2.10)."""

    BASE_EVENT = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:event-1@example.com
DTSTAMP:20260101T120000Z
LAST-MODIFIED:20260101T120000Z
SEQUENCE:0
DTSTART:20260601T100000Z
DTEND:20260601T110000Z
SUMMARY:Project sync
ORGANIZER:mailto:alice@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:alice@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com
DESCRIPTION:original notes
END:VEVENT
END:VCALENDAR
"""

    def _sig(self, body):
        return scheduling.extract_scheduling_signature(Calendar.from_ical(body))

    def test_stable_across_dtstamp_changes(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(self.BASE_EVENT.replace(b"20260101T120000Z", b"20260102T130000Z"))
        self.assertEqual(a, b)

    def test_changes_when_description_changes(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(self.BASE_EVENT.replace(b"original notes", b"updated notes"))
        self.assertNotEqual(a, b)

    def test_changes_when_attendee_added(self):
        a = self._sig(self.BASE_EVENT)
        body = (
            self.BASE_EVENT.decode()
            .replace(
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n",
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n"
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:carol@example.com\n",
            )
            .encode()
        )
        self.assertNotEqual(a, self._sig(body))

    def test_changes_when_dtstart_changes(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(
            self.BASE_EVENT.replace(
                b"DTSTART:20260601T100000Z", b"DTSTART:20260601T110000Z"
            )
        )
        self.assertNotEqual(a, b)

    def test_changes_when_sequence_bumps(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(self.BASE_EVENT.replace(b"SEQUENCE:0", b"SEQUENCE:1"))
        self.assertNotEqual(a, b)

    def test_attendee_order_independent(self):
        reordered = (
            self.BASE_EVENT.decode()
            .replace(
                "ATTENDEE;PARTSTAT=ACCEPTED:mailto:alice@example.com\n"
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n",
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n"
                "ATTENDEE;PARTSTAT=ACCEPTED:mailto:alice@example.com\n",
            )
            .encode()
        )
        self.assertEqual(self._sig(self.BASE_EVENT), self._sig(reordered))

    def test_partstat_change_changes_signature(self):
        replied = self.BASE_EVENT.replace(
            b"ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com",
            b"ATTENDEE;PARTSTAT=ACCEPTED:mailto:bob@example.com",
        )
        self.assertNotEqual(self._sig(self.BASE_EVENT), self._sig(replied))

    def test_only_vtimezone_yields_empty_digest(self):
        body = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VTIMEZONE
TZID:UTC
END:VTIMEZONE
END:VCALENDAR
"""
        self.assertEqual(self._sig(body), hashlib.sha256().digest())

    def test_recurrence_id_distinguishes_overrides(self):
        body_with_override = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:rec@example.com
DTSTAMP:20260101T120000Z
DTSTART:20260601T100000Z
SUMMARY:Series
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
BEGIN:VEVENT
UID:rec@example.com
DTSTAMP:20260101T120000Z
RECURRENCE-ID:20260602T100000Z
DTSTART:20260602T120000Z
SUMMARY:Series (override)
END:VEVENT
END:VCALENDAR
"""
        body_without_override = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:rec@example.com
DTSTAMP:20260101T120000Z
DTSTART:20260601T100000Z
SUMMARY:Series
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR
"""
        self.assertNotEqual(
            self._sig(body_with_override), self._sig(body_without_override)
        )


FREEBUSY_REQUEST = b"""\
BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Test//EN\r
METHOD:REQUEST\r
BEGIN:VFREEBUSY\r
UID:fb-1@example.com\r
DTSTAMP:20260601T080000Z\r
DTSTART:20260601T000000Z\r
DTEND:20260602T000000Z\r
ORGANIZER:mailto:alice@example.com\r
ATTENDEE:mailto:alice@example.com\r
ATTENDEE:mailto:bob@example.com\r
END:VFREEBUSY\r
END:VCALENDAR\r
"""


class _FakeRequest:
    headers: dict[str, str] = {}


class _FakeOutbox(scheduling.ScheduleOutbox):
    """Outbox where the principal is alice@example.com with one busy hour."""

    def __init__(self, busy_periods=None):
        from datetime import datetime, timezone

        from icalendar.prop import vPeriod

        self._busy = busy_periods or [
            vPeriod(
                (
                    datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
                    datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
                )
            )
        ]

    async def get_attendee_busy_periods(self, attendee_address, start, end):
        if attendee_address == "mailto:alice@example.com":
            return self._busy
        return None


CALDAV_NS = "{urn:ietf:params:xml:ns:caldav}"


class ScheduleOutboxFreeBusyTests(unittest.TestCase):
    """Tests for ScheduleOutbox free-busy POST handling (RFC 6638 §6)."""

    def _post(self, outbox, body=FREEBUSY_REQUEST, content_type="text/calendar"):
        return asyncio.run(
            outbox.handle_post(_FakeRequest(), {}, "/p/outbox/", [body], content_type)
        )

    def test_success_returns_schedule_response(self):
        outbox = _FakeOutbox()
        response = self._post(outbox)

        self.assertEqual(200, response.status)
        body_xml = b"".join(response.body)
        root = ET.fromstring(body_xml)
        self.assertEqual(CALDAV_NS + "schedule-response", root.tag)
        responses = root.findall(CALDAV_NS + "response")
        self.assertEqual(2, len(responses))

        recipients = {
            r.find(CALDAV_NS + "recipient/{DAV:}href").text: r for r in responses
        }
        # Local user gets a calendar-data REPLY.
        alice = recipients["mailto%3Aalice%40example.com"]
        self.assertEqual(
            scheduling.REQUEST_STATUS_SUCCESS,
            alice.find(CALDAV_NS + "request-status").text,
        )
        cd = alice.find(CALDAV_NS + "calendar-data").text
        self.assertIn("METHOD:REPLY", cd)
        self.assertIn("20260601T100000Z/20260601T110000Z", cd)
        self.assertIn("FREEBUSY", cd)

        # Unknown user gets 3.8 No authority and no calendar-data.
        bob = recipients["mailto%3Abob%40example.com"]
        self.assertEqual(
            scheduling.REQUEST_STATUS_NO_AUTHORITY,
            bob.find(CALDAV_NS + "request-status").text,
        )
        self.assertIsNone(bob.find(CALDAV_NS + "calendar-data"))

    def test_rejects_non_calendar_content_type(self):
        response = self._post(_FakeOutbox(), content_type="application/json")
        self.assertEqual(415, response.status)

    def test_rejects_request_without_method_request(self):
        body = FREEBUSY_REQUEST.replace(b"METHOD:REQUEST\r\n", b"")
        with self.assertRaises(webdav.BadRequestError):
            self._post(_FakeOutbox(), body=body)

    def test_rejects_missing_attendee(self):
        body = FREEBUSY_REQUEST.replace(
            b"ATTENDEE:mailto:alice@example.com\r\nATTENDEE:mailto:bob@example.com\r\n",
            b"",
        )
        with self.assertRaises(webdav.BadRequestError):
            self._post(_FakeOutbox(), body=body)

    def test_rejects_missing_organizer(self):
        body = FREEBUSY_REQUEST.replace(b"ORGANIZER:mailto:alice@example.com\r\n", b"")
        with self.assertRaises(webdav.BadRequestError):
            self._post(_FakeOutbox(), body=body)

    def test_rejects_extra_components(self):
        body = FREEBUSY_REQUEST.replace(
            b"END:VCALENDAR\r\n",
            b"BEGIN:VEVENT\r\nUID:e\r\nDTSTAMP:20260101T000000Z\r\nDTSTART:20260101T000000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
        )
        with self.assertRaises(webdav.BadRequestError):
            self._post(_FakeOutbox(), body=body)

    def test_default_get_attendee_busy_periods_returns_none(self):
        # The base class refuses to answer for any attendee.
        outbox = scheduling.ScheduleOutbox()
        result = asyncio.run(
            outbox.get_attendee_busy_periods("mailto:anyone@example.com", None, None)
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
