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

import unittest
from wsgiref.util import setup_testing_defaults

from icalendar.cal import Calendar as ICalendar

from xandikos import caldav
from xandikos.tests import test_webdav

from ..caldav import CalendarDataProperty
from ..webdav import ET, Property, WebDAVApp


class WebTests(test_webdav.WebTestCase):
    def makeApp(self, backend):
        app = WebDAVApp(backend)
        app.register_methods([caldav.MkcalendarMethod()])
        return app

    def mkcalendar(self, app, path):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "MKCALENDAR",
            "SCRIPT_NAME": "",
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def test_mkcalendar_ok(self):
        class Backend:
            def create_collection(self, relpath):
                pass

            def get_resource(self, relpath):
                return None

        class ResourceTypeProperty(Property):
            name = "{DAV:}resourcetype"

            async def get_value(unused_self, href, resource, ret, environ):
                ET.SubElement(ret, "{DAV:}collection")

            async def set_value(unused_self, href, resource, ret):
                self.assertEqual(
                    [
                        "{DAV:}collection",
                        "{urn:ietf:params:xml:ns:caldav}calendar",
                    ],
                    [x.tag for x in ret],
                )

        app = self.makeApp(Backend())
        app.register_properties([ResourceTypeProperty()])
        code, headers, contents = self.mkcalendar(app, "/resource/bla")
        self.assertEqual("201 Created", code)
        self.assertEqual(b"", contents)


class ExtractfromCalendarTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.requested = ET.Element("{%s}calendar-data" % caldav.NAMESPACE)

    def extractEqual(self, incal_str, outcal_str):
        incal = ICalendar.from_ical(incal_str)
        expected_outcal = ICalendar.from_ical(outcal_str)
        outcal = ICalendar()
        outcal = caldav.extract_from_calendar(incal, self.requested)
        self.maxDiff = None
        self.assertMultiLineEqual(
            expected_outcal.to_ical().decode(),
            outcal.to_ical().decode(),
            ET.tostring(self.requested),
        )

    def test_comp(self):
        comp = ET.SubElement(self.requested, "{%s}comp" % caldav.NAMESPACE)
        comp.set("name", "VCALENDAR")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
CLASS:PUBLIC
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
END:VCALENDAR
""",
        )

    def test_comp_nested(self):
        vcal_comp = ET.SubElement(self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        vtodo_comp = ET.SubElement(vcal_comp, "{%s}comp" % caldav.NAMESPACE)
        vtodo_comp.set("name", "VTODO")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
END:VTODO
END:VCALENDAR
""",
        )
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VEVENT
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
END:VCALENDAR
""",
        )

    def test_prop(self):
        vcal_comp = ET.SubElement(self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        vtodo_comp = ET.SubElement(vcal_comp, "{%s}comp" % caldav.NAMESPACE)
        vtodo_comp.set("name", "VTODO")
        completed_prop = ET.SubElement(vtodo_comp, "{%s}prop" % caldav.NAMESPACE)
        completed_prop.set("name", "COMPLETED")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
END:VTODO
END:VCALENDAR
""",
        )
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VEVENT
CREATED:20090606T042958Z
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
END:VCALENDAR
""",
        )

    def test_allprop(self):
        vcal_comp = ET.SubElement(self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        vtodo_comp = ET.SubElement(vcal_comp, "{%s}comp" % caldav.NAMESPACE)
        vtodo_comp.set("name", "VTODO")
        ET.SubElement(vtodo_comp, "{%s}allprop" % caldav.NAMESPACE)
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
        )

    def test_allcomp(self):
        vcal_comp = ET.SubElement(self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        ET.SubElement(vcal_comp, "{%s}allcomp" % caldav.NAMESPACE)
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
END:VTODO
END:VCALENDAR
""",
        )

    def test_expand(self):
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20060103T000000Z")
        expand.set("end", "20060105T000000Z")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART;TZID=US/Eastern:20060102T120000
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:Event #2
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART;TZID=US/Eastern:20060104T140000
DURATION:PT1H
RECURRENCE-ID;TZID=US/Eastern:20060104T120000
SUMMARY:Event #2 bis
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART;TZID=US/Eastern:20060103T120000
DURATION:PT1H
RECURRENCE-ID:20060103T170000
SUMMARY:Event #2
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART;TZID=US/Eastern:20060104T140000
DURATION:PT1H
RECURRENCE-ID:20060104T170000
SUMMARY:Event #2 bis
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
END:VCALENDAR
""",
        )

    def test_expand_floating(self):
        """Test expansion of recurring events with floating time (no timezone)."""
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20060103T000000Z")
        expand.set("end", "20060105T000000Z")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART:20060102T170000
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:Event #3 floating
UID:FLOATING-EVENT@example.com
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART:20060104T190000
DURATION:PT1H
RECURRENCE-ID:20060104T170000
SUMMARY:Event #3 floating modified
UID:FLOATING-EVENT@example.com
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART:20060103T170000
DURATION:PT1H
RECURRENCE-ID:20060103T170000
SUMMARY:Event #3 floating
UID:FLOATING-EVENT@example.com
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART:20060104T190000
DURATION:PT1H
RECURRENCE-ID:20060104T170000
SUMMARY:Event #3 floating modified
UID:FLOATING-EVENT@example.com
END:VEVENT
END:VCALENDAR
""",
        )

    def test_limit_recurrence_set(self):
        """Test limit-recurrence-set element."""
        limit = ET.SubElement(
            self.requested, "{%s}limit-recurrence-set" % caldav.NAMESPACE
        )
        limit.set("start", "20060201T000000Z")
        limit.set("end", "20060301T000000Z")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTART:20060101T120000Z
DURATION:PT1H
RRULE:FREQ=WEEKLY
DTSTAMP:20060101T120000Z
SUMMARY:Weekly meeting
UID:weekly-meeting@example.com
END:VEVENT
BEGIN:VEVENT
DTSTART:20060115T140000Z
DURATION:PT2H
RECURRENCE-ID:20060115T120000Z
DTSTAMP:20060101T120000Z
SUMMARY:Weekly meeting (extended)
UID:weekly-meeting@example.com
END:VEVENT
BEGIN:VEVENT
DTSTART:20060212T120000Z
DURATION:PT1H
RECURRENCE-ID:20060212T120000Z
DTSTAMP:20060101T120000Z
SUMMARY:Weekly meeting (February)
UID:weekly-meeting@example.com
END:VEVENT
BEGIN:VEVENT
DTSTART:20060312T120000Z
DURATION:PT1H
RECURRENCE-ID:20060312T120000Z
DTSTAMP:20060101T120000Z
SUMMARY:Weekly meeting (March)
UID:weekly-meeting@example.com
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTART:20060101T120000Z
DURATION:PT1H
RRULE:FREQ=WEEKLY
DTSTAMP:20060101T120000Z
SUMMARY:Weekly meeting
UID:weekly-meeting@example.com
END:VEVENT
BEGIN:VEVENT
DTSTART:20060212T120000Z
DURATION:PT1H
RECURRENCE-ID:20060212T120000Z
DTSTAMP:20060101T120000Z
SUMMARY:Weekly meeting (February)
UID:weekly-meeting@example.com
END:VEVENT
END:VCALENDAR
""",
        )


class TestCalendarDataProperty(unittest.TestCase):
    def test_supported_on_with_calendar(self):
        """Test that supported_on returns True for calendar resources."""
        prop = CalendarDataProperty()

        class CalendarResource:
            def get_content_type(self):
                return "text/calendar"

        self.assertTrue(prop.supported_on(CalendarResource()))

    def test_supported_on_with_non_calendar(self):
        """Test that supported_on returns False for non-calendar resources."""
        prop = CalendarDataProperty()

        class NonCalendarResource:
            def get_content_type(self):
                return "text/plain"

        self.assertFalse(prop.supported_on(NonCalendarResource()))

    def test_supported_on_with_missing_content_type(self):
        """Test that supported_on handles resources without content type gracefully."""
        prop = CalendarDataProperty()

        class ResourceWithoutContentType:
            def get_content_type(self):
                raise KeyError("No content type")

        # This should not raise an exception, but return False
        self.assertFalse(prop.supported_on(ResourceWithoutContentType()))


class ExtractFromCalendarExpandTests(unittest.TestCase):
    """Comprehensive tests for calendar-data expand functionality."""

    def setUp(self):
        self.requested = ET.Element("{%s}calendar-data" % caldav.NAMESPACE)

    def test_expand_with_timezone_aware_events(self):
        """Test expansion of recurring events with timezone information."""
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20240115T000000Z")
        expand.set("end", "20240120T000000Z")

        incal = ICalendar.from_ical(b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:STANDARD
DTSTART:20231105T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20240310T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:timezone-event@example.com
DTSTART;TZID=America/New_York:20240115T100000
DTEND;TZID=America/New_York:20240115T110000
SUMMARY:Daily Meeting
RRULE:FREQ=DAILY;COUNT=5
END:VEVENT
END:VCALENDAR
""")

        result = caldav.extract_from_calendar(incal, self.requested)
        events = [comp for comp in result.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 5)

        # Verify timezone is preserved
        for event in events:
            # Check that DTSTART has timezone parameter
            self.assertIn("TZID", event["DTSTART"].params)

    def test_expand_no_recurrence(self):
        """Test that expand works correctly with non-recurring events."""
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20240101T000000Z")
        expand.set("end", "20240131T000000Z")

        incal = ICalendar.from_ical(b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:single-event@example.com
DTSTART:20240115T140000Z
DTEND:20240115T150000Z
SUMMARY:Single Event
END:VEVENT
END:VCALENDAR
""")

        result = caldav.extract_from_calendar(incal, self.requested)
        events = [comp for comp in result.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["SUMMARY"], "Single Event")

    def test_expand_with_recurrence_override(self):
        """Test expansion with RECURRENCE-ID overrides."""
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20240101T000000Z")
        expand.set("end", "20240110T000000Z")

        incal = ICalendar.from_ical(b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:override-event@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
SUMMARY:Daily Event
RRULE:FREQ=DAILY;COUNT=5
END:VEVENT
BEGIN:VEVENT
UID:override-event@example.com
RECURRENCE-ID:20240103T100000Z
DTSTART:20240103T140000Z
DTEND:20240103T150000Z
SUMMARY:Daily Event (Rescheduled)
LOCATION:Different Room
END:VEVENT
END:VCALENDAR
""")

        result = caldav.extract_from_calendar(incal, self.requested)
        events = [comp for comp in result.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 5)

        # Find the overridden event
        overridden = None
        for event in events:
            if event.get("LOCATION") == "Different Room":
                overridden = event
                break

        self.assertIsNotNone(overridden)
        self.assertEqual(overridden["SUMMARY"], "Daily Event (Rescheduled)")
        # Verify time was changed
        self.assertEqual(overridden["DTSTART"].dt.hour, 14)  # Changed from 10 to 14

    def test_expand_invalid_time_range(self):
        """Test expansion with invalid time range raises assertion."""
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20240101T000000Z")
        expand.set("end", "20240101T000000Z")  # Same as start - invalid

        incal = ICalendar.from_ical(b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
SUMMARY:Event
RRULE:FREQ=DAILY;COUNT=10
END:VEVENT
END:VCALENDAR
""")

        # Should raise AssertionError for invalid time range
        with self.assertRaises(AssertionError):
            caldav.extract_from_calendar(incal, self.requested)


class CalendarAttachmentTests(unittest.TestCase):
    """Tests for CalDAV managed attachments functionality."""

    def setUp(self):
        super().setUp()
        import tempfile
        from xandikos.web import CalendarCollection
        from xandikos.store.vdir import VdirStore

        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.store = VdirStore(self.temp_dir)

        # Mock backend
        class MockBackend:
            pass

        backend = MockBackend()
        self.calendar = CalendarCollection(backend, "/calendar", self.store)
        self.calendar.href = "/calendar"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)
        super().tearDown()

    def test_supports_managed_attachments(self):
        """Test that CalendarCollection supports managed attachments."""
        self.assertTrue(self.calendar.supports_managed_attachments())

    def test_get_managed_attachments_server_url(self):
        """Test getting the managed attachments server URL."""
        url = self.calendar.get_managed_attachments_server_url()
        self.assertEqual(url, "/calendar?action=attachment")

    def test_create_attachment(self):
        """Test creating a new attachment."""
        attachment_data = b"test attachment data"
        content_type = "text/plain"
        filename = "test.txt"

        managed_id, attachment_url = self.calendar.create_attachment(
            attachment_data, content_type, filename
        )

        self.assertIsNotNone(managed_id)
        self.assertTrue(managed_id)  # Should not be empty
        self.assertEqual(
            attachment_url, f"/calendar?action=attachment&managed-id={managed_id}"
        )

    def test_get_attachment(self):
        """Test retrieving an attachment."""
        attachment_data = b"test attachment data"
        content_type = "text/plain"
        filename = "test.txt"

        # Create attachment
        managed_id, _ = self.calendar.create_attachment(
            attachment_data, content_type, filename
        )

        # Retrieve attachment
        retrieved_data, retrieved_content_type, retrieved_filename = (
            self.calendar.get_attachment(managed_id)
        )

        self.assertEqual(retrieved_data, attachment_data)
        self.assertEqual(retrieved_content_type, content_type)
        self.assertEqual(retrieved_filename, filename)

    def test_get_nonexistent_attachment(self):
        """Test retrieving a non-existent attachment raises KeyError."""
        with self.assertRaises(KeyError):
            self.calendar.get_attachment("nonexistent-id")

    def test_update_attachment(self):
        """Test updating an existing attachment."""
        # Create initial attachment
        initial_data = b"initial data"
        managed_id, _ = self.calendar.create_attachment(
            initial_data, "text/plain", "initial.txt"
        )

        # Update attachment
        updated_data = b"updated data"
        updated_content_type = "text/plain"
        updated_filename = "updated.txt"

        self.calendar.update_attachment(
            managed_id, updated_data, updated_content_type, updated_filename
        )

        # Verify update
        retrieved_data, retrieved_content_type, retrieved_filename = (
            self.calendar.get_attachment(managed_id)
        )

        self.assertEqual(retrieved_data, updated_data)
        self.assertEqual(retrieved_content_type, updated_content_type)
        self.assertEqual(retrieved_filename, updated_filename)

    def test_update_nonexistent_attachment(self):
        """Test updating a non-existent attachment raises KeyError."""
        with self.assertRaises(KeyError):
            self.calendar.update_attachment("nonexistent-id", b"data", "text/plain")

    def test_delete_attachment(self):
        """Test deleting an attachment."""
        # Create attachment
        managed_id, _ = self.calendar.create_attachment(
            b"test data", "text/plain", "test.txt"
        )

        # Delete attachment
        self.calendar.delete_attachment(managed_id)

        # Verify deletion
        with self.assertRaises(KeyError):
            self.calendar.get_attachment(managed_id)

    def test_delete_nonexistent_attachment(self):
        """Test deleting a non-existent attachment raises KeyError."""
        with self.assertRaises(KeyError):
            self.calendar.delete_attachment("nonexistent-id")

    def test_create_attachment_without_filename(self):
        """Test creating an attachment without a filename."""
        attachment_data = b"test data"
        content_type = "application/octet-stream"

        managed_id, _ = self.calendar.create_attachment(
            attachment_data, content_type, None
        )

        retrieved_data, retrieved_content_type, retrieved_filename = (
            self.calendar.get_attachment(managed_id)
        )

        self.assertEqual(retrieved_data, attachment_data)
        self.assertEqual(retrieved_content_type, content_type)
        self.assertIsNone(retrieved_filename)
