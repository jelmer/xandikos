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
import unittest

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

                def get_schedule_tag(self):
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


if __name__ == "__main__":
    unittest.main()
