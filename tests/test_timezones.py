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

"""Tests for xandikos.timezones (RFC 7809 CalDAV Time Zone Extensions)."""

import asyncio
import unittest

from xandikos import caldav, timezones, webdav
from xandikos.webdav import ET


class TimezoneServiceSetPropertyTests(unittest.TestCase):
    """Tests for TimezoneServiceSetProperty (RFC 7809 Section 5.1)."""

    def test_property_name(self):
        """Test timezone-service-set property name."""
        prop = timezones.TimezoneServiceSetProperty([])
        self.assertEqual(prop.name, "{DAV:}timezone-service-set")

    def test_property_attributes(self):
        """Test timezone-service-set property attributes.

        RFC 7809 Section 5.1: The timezone-service-set property provides
        a way to discover available timezone services.
        """
        prop = timezones.TimezoneServiceSetProperty([])
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)
        self.assertEqual(prop.resource_type, webdav.COLLECTION_RESOURCE_TYPE)

    def test_get_value_empty_services(self):
        """Test timezone-service-set with no timezone services.

        RFC 7809 Section 5.1: The property can be empty if no
        timezone services are available.
        """

        async def run_test():
            prop = timezones.TimezoneServiceSetProperty([])

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 0)

        asyncio.run(run_test())

    def test_get_value_single_service(self):
        """Test timezone-service-set with single timezone service.

        RFC 7809 Section 5.1: The property contains one or more
        DAV:href elements pointing to timezone services.
        """

        async def run_test():
            prop = timezones.TimezoneServiceSetProperty(["/timezones/"])

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/timezones/")

        asyncio.run(run_test())

    def test_get_value_multiple_services(self):
        """Test timezone-service-set with multiple timezone services.

        RFC 7809 Section 5.1: A server can provide multiple
        timezone service endpoints.
        """

        async def run_test():
            prop = timezones.TimezoneServiceSetProperty(
                ["/timezones/", "/tz-service/", "https://example.com/tz/"]
            )

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 3)
            # Check exact values in order
            self.assertEqual(hrefs[0].text, "/timezones/")
            self.assertEqual(hrefs[1].text, "/tz-service/")
            self.assertEqual(hrefs[2].text, "https://example.com/tz/")

        asyncio.run(run_test())

    def test_get_value_relative_url(self):
        """Test timezone-service-set with relative URL resolution."""

        async def run_test():
            prop = timezones.TimezoneServiceSetProperty(["timezones/"])

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            # Relative URLs should be resolved against base_href
            self.assertEqual(hrefs[0].text, "/calendars/user1/timezones/")

        asyncio.run(run_test())

    def test_initialization_with_services(self):
        """Test that TimezoneServiceSetProperty stores services correctly."""
        services = ["/timezones/", "/tz/"]
        prop = timezones.TimezoneServiceSetProperty(services)
        self.assertEqual(prop._timezone_services, services)

    def test_get_value_preserves_order(self):
        """Test that timezone services are returned in the order provided."""

        async def run_test():
            services = ["/tz1/", "/tz2/", "/tz3/"]
            prop = timezones.TimezoneServiceSetProperty(services)

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 3)
            # Verify order is preserved
            self.assertEqual(hrefs[0].text, "/tz1/")
            self.assertEqual(hrefs[1].text, "/tz2/")
            self.assertEqual(hrefs[2].text, "/tz3/")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()


class CalendarTimezoneIdPropertyTests(unittest.TestCase):
    """Tests for CalendarTimezoneIdProperty (RFC 7809 Section 5.2)."""

    def setUp(self):
        super().setUp()
        self.prop = caldav.CalendarTimezoneIdProperty()

    def test_property_attributes(self):
        self.assertEqual(
            "{urn:ietf:params:xml:ns:caldav}calendar-timezone-id", self.prop.name
        )
        self.assertFalse(self.prop.in_allprops)

    def test_get_value(self):
        class Resource:
            def get_calendar_timezone_id(self):
                return "Europe/Amsterdam"

        el = ET.Element(self.prop.name)
        asyncio.run(self.prop.get_value("/", Resource(), el, {}))
        self.assertEqual("Europe/Amsterdam", el.text)

    def test_set_value(self):
        class Resource:
            timezone_id = None

            def set_calendar_timezone_id(self, timezone_id):
                self.timezone_id = timezone_id

        resource = Resource()
        el = ET.Element(self.prop.name)
        el.text = "Europe/Amsterdam"
        asyncio.run(self.prop.set_value("/", resource, el))
        self.assertEqual("Europe/Amsterdam", resource.timezone_id)

    def test_remove_value(self):
        class Resource:
            timezone_id = "Europe/Amsterdam"

            def set_calendar_timezone_id(self, timezone_id):
                self.timezone_id = timezone_id

        resource = Resource()
        asyncio.run(self.prop.set_value("/", resource, None))
        self.assertIsNone(resource.timezone_id)

    def test_unknown_timezone_raises_precondition(self):
        """An unrecognized identifier fails the valid-timezone precondition."""

        class Resource:
            def set_calendar_timezone_id(self, timezone_id):
                raise caldav.UnknownTimezoneError(timezone_id)

        el = ET.Element(self.prop.name)
        el.text = "Nonexistent/Timezone"
        with self.assertRaises(webdav.PreconditionFailure) as cm:
            asyncio.run(self.prop.set_value("/", Resource(), el))
        self.assertEqual(
            "{urn:ietf:params:xml:ns:caldav}valid-timezone", cm.exception.precondition
        )


class CalendarTimezonePropertyTests(unittest.TestCase):
    """Tests for CalendarTimezoneProperty error handling."""

    def test_invalid_timezone_raises_precondition(self):
        """Unparseable calendar data fails the valid-calendar-data precondition."""

        class Resource:
            def set_calendar_timezone(self, content):
                raise caldav.InvalidTimezoneError("could not parse")

        prop = caldav.CalendarTimezoneProperty()
        el = ET.Element(prop.name)
        el.text = "junk"
        with self.assertRaises(webdav.PreconditionFailure) as cm:
            asyncio.run(prop.set_value("/", Resource(), el))
        self.assertEqual(
            "{urn:ietf:params:xml:ns:caldav}valid-calendar-data",
            cm.exception.precondition,
        )
