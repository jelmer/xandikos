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
from datetime import datetime, timedelta, timezone
from wsgiref.util import setup_testing_defaults

from icalendar.cal import Calendar as ICalendar, Component

from xandikos import caldav
from . import test_webdav

from xandikos.caldav import (
    CalendarDataProperty,
    process_vavailability_components,
    CALENDAR_RESOURCE_TYPE,
    SCHEDULE_INBOX_RESOURCE_TYPE,
    CalendarAvailabilityProperty,
)


from xandikos.webdav import ET, Property, WebDAVApp


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

    def test_limit_freebusy_set(self):
        """Test limit-freebusy-set element filters FREEBUSY properties."""
        limit = ET.SubElement(
            self.requested, "{%s}limit-freebusy-set" % caldav.NAMESPACE
        )
        # Request range: 10:00 - 12:00
        limit.set("start", "20240115T100000Z")
        limit.set("end", "20240115T120000Z")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VFREEBUSY
UID:freebusy@example.com
DTSTART:20240115T080000Z
DTEND:20240115T140000Z
FREEBUSY:20240115T090000Z/20240115T093000Z
FREEBUSY:20240115T095000Z/20240115T103000Z
FREEBUSY:20240115T110000Z/20240115T120000Z
FREEBUSY:20240115T120000Z/20240115T130000Z
FREEBUSY:20240115T133000Z/20240115T140000Z
END:VFREEBUSY
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VFREEBUSY
UID:freebusy@example.com
DTSTART:20240115T080000Z
DTEND:20240115T140000Z
FREEBUSY:20240115T095000Z/20240115T103000Z
FREEBUSY:20240115T110000Z/20240115T120000Z
END:VFREEBUSY
END:VCALENDAR
""",
        )

    def test_limit_freebusy_set_preserves_other_components(self):
        """Test that limit-freebusy-set preserves non-VFREEBUSY components."""
        limit = ET.SubElement(
            self.requested, "{%s}limit-freebusy-set" % caldav.NAMESPACE
        )
        limit.set("start", "20240115T100000Z")
        limit.set("end", "20240115T120000Z")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTART:20240115T090000Z
DTEND:20240115T100000Z
SUMMARY:Morning meeting
UID:event1@example.com
END:VEVENT
BEGIN:VFREEBUSY
UID:freebusy@example.com
DTSTART:20240115T080000Z
DTEND:20240115T140000Z
FREEBUSY:20240115T090000Z/20240115T093000Z
FREEBUSY:20240115T110000Z/20240115T120000Z
END:VFREEBUSY
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTART:20240115T090000Z
DTEND:20240115T100000Z
SUMMARY:Morning meeting
UID:event1@example.com
END:VEVENT
BEGIN:VFREEBUSY
UID:freebusy@example.com
DTSTART:20240115T080000Z
DTEND:20240115T140000Z
FREEBUSY:20240115T110000Z/20240115T120000Z
END:VFREEBUSY
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

    def test_get_value_ext_with_expand(self):
        """Test that get_value_ext properly handles expand elements."""
        import asyncio

        prop = CalendarDataProperty()

        # Create a mock resource with recurring event
        ical_data = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-recurring@example.com
DTSTART:20230101T100000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:Recurring Event
END:VEVENT
END:VCALENDAR"""

        class MockFile:
            def __init__(self, cal_data):
                self.calendar = ICalendar.from_ical(cal_data)

        class MockResource:
            def __init__(self):
                self._file = MockFile(ical_data)

            def get_content_type(self):
                return "text/calendar"

            async def get_body(self):
                return [ical_data]

            async def get_file(self):
                return self._file

        # Create calendar-data element with expand
        requested = ET.Element("{%s}calendar-data" % caldav.NAMESPACE)
        expand = ET.SubElement(requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20230102T000000Z")
        expand.set("end", "20230104T000000Z")

        # Create output element
        el = ET.Element("test")

        async def run_test():
            # Call get_value_ext
            await prop.get_value_ext("/test", MockResource(), el, {}, requested)

        asyncio.run(run_test())

        # Parse the result
        result_cal = ICalendar.from_ical(el.text)

        # Should have expanded events for Jan 2 and Jan 3
        events = list(result_cal.walk("VEVENT"))
        self.assertEqual(2, len(events))

        # Check that events have RECURRENCE-ID
        for event in events:
            self.assertIn("RECURRENCE-ID", event)

    def test_calendar_query_with_expand(self):
        """Test that calendar-query REPORT properly handles expand in calendar-data."""
        import asyncio
        from xml.etree import ElementTree as ET

        # Create a mock CalDAV app/reporter setup
        ical_data = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:recurring@example.com
DTSTART:20230101T100000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=7
SUMMARY:Daily Meeting
END:VEVENT
END:VCALENDAR"""

        class MockFile:
            def __init__(self):
                self.calendar = ICalendar.from_ical(ical_data)

        class MockResource:
            def __init__(self):
                self._file = MockFile()
                self.content_type = "text/calendar"

            def get_content_type(self):
                return self.content_type

            async def get_file(self):
                return self._file

            async def get_body(self):
                return [ical_data]

        # Create the calendar-query request body
        query = ET.Element("{urn:ietf:params:xml:ns:caldav}calendar-query")
        prop_el = ET.SubElement(query, "{DAV:}prop")
        caldata_el = ET.SubElement(
            prop_el, "{urn:ietf:params:xml:ns:caldav}calendar-data"
        )
        expand_el = ET.SubElement(caldata_el, "{urn:ietf:params:xml:ns:caldav}expand")
        expand_el.set("start", "20230103T000000Z")
        expand_el.set("end", "20230105T000000Z")

        # The reporter would process this and call get_properties_with_data
        # which would eventually call CalendarDataProperty.get_value_ext
        # For this test, we'll verify that the expand works correctly
        prop = CalendarDataProperty()
        el = ET.Element("test")

        async def run_test():
            await prop.get_value_ext("/test", MockResource(), el, {}, caldata_el)

        asyncio.run(run_test())

        # Verify the expanded result
        result_cal = ICalendar.from_ical(el.text)
        events = list(result_cal.walk("VEVENT"))

        # Should have 2 events (Jan 3 and Jan 4)
        self.assertEqual(2, len(events))

        # Check that each event has the expected date
        dates = sorted([event["DTSTART"].dt for event in events])
        self.assertEqual(
            datetime(2023, 1, 3, 10, 0, 0, tzinfo=timezone(timedelta(0))), dates[0]
        )
        self.assertEqual(
            datetime(2023, 1, 4, 10, 0, 0, tzinfo=timezone(timedelta(0))), dates[1]
        )


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


class ProcessVavailabilityComponentsTests(unittest.TestCase):
    """Tests for priority-based VAVAILABILITY processing."""

    def _tzify(self, dt):
        """Convert datetime to UTC."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def test_single_vavailability(self):
        """Test processing a single VAVAILABILITY component."""
        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))
        vavail.add("BUSYTYPE", "BUSY-UNAVAILABLE")

        start = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components([vavail], start, end, self._tzify)

        self.assertEqual(len(periods), 1)
        self.assertEqual(
            periods[0],
            (
                datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
                "BUSY-UNAVAILABLE",
            ),
        )

    def test_vavailability_with_available(self):
        """Test VAVAILABILITY with AVAILABLE subcomponents."""
        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))
        vavail.add("BUSYTYPE", "BUSY-UNAVAILABLE")

        # Add AVAILABLE period from 12:00 to 13:00
        available = Component()
        available.name = "AVAILABLE"
        available.add("DTSTART", datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        available.add("DTEND", datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))
        vavail.add_component(available)

        start = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components([vavail], start, end, self._tzify)

        # Should have two busy periods with a gap for the available time
        self.assertEqual(len(periods), 2)
        self.assertEqual(
            periods[0],
            (
                datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                "BUSY-UNAVAILABLE",
            ),
        )
        self.assertEqual(
            periods[1],
            (
                datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
                "BUSY-UNAVAILABLE",
            ),
        )

    def test_priority_override(self):
        """Test higher priority VAVAILABILITY overriding lower priority."""
        # Low priority (9) - busy all day
        vavail_low = Component()
        vavail_low.name = "VAVAILABILITY"
        vavail_low.add("DTSTART", datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
        vavail_low.add("DTEND", datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc))
        vavail_low.add("BUSYTYPE", "BUSY-UNAVAILABLE")
        vavail_low.add("PRIORITY", 9)

        # High priority (1) - available 9-17
        vavail_high = Component()
        vavail_high.name = "VAVAILABILITY"
        vavail_high.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail_high.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))
        vavail_high.add("BUSYTYPE", "BUSY")
        vavail_high.add("PRIORITY", 1)

        start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components(
            [vavail_low, vavail_high], start, end, self._tzify
        )

        # Should have three periods: unavailable, busy, unavailable
        self.assertEqual(len(periods), 3)
        self.assertEqual(
            periods[0],
            (
                datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                "BUSY-UNAVAILABLE",
            ),
        )
        self.assertEqual(
            periods[1],
            (
                datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
                "BUSY",
            ),
        )
        self.assertEqual(
            periods[2],
            (
                datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc),
                "BUSY-UNAVAILABLE",
            ),
        )

    def test_same_priority_fbtype_precedence(self):
        """Test that BUSY > BUSY-UNAVAILABLE > BUSY-TENTATIVE for same priority."""
        # Two components with same priority but different BUSYTYPE
        vavail1 = Component()
        vavail1.name = "VAVAILABILITY"
        vavail1.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail1.add("DTEND", datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        vavail1.add("BUSYTYPE", "BUSY-TENTATIVE")
        vavail1.add("PRIORITY", 5)

        vavail2 = Component()
        vavail2.name = "VAVAILABILITY"
        vavail2.add("DTSTART", datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc))
        vavail2.add("DTEND", datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc))
        vavail2.add("BUSYTYPE", "BUSY")
        vavail2.add("PRIORITY", 5)

        start = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components(
            [vavail1, vavail2], start, end, self._tzify
        )

        # BUSY should override BUSY-TENTATIVE for the overlapping period
        self.assertEqual(len(periods), 3)
        self.assertEqual(periods[0][2], "BUSY-TENTATIVE")  # 9-10
        self.assertEqual(periods[1][2], "BUSY")  # 10-11
        self.assertEqual(periods[2][2], "BUSY-TENTATIVE")  # 11-12

    def test_invalid_priority_values(self):
        """Test handling of invalid PRIORITY values with logging."""
        # Capture log output
        with self.assertLogs("xandikos.caldav", level="WARNING") as cm:
            # Test string that can't be converted to int (simulate malformed input)
            vavail1 = Component()
            vavail1.name = "VAVAILABILITY"
            vavail1.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
            vavail1.add("DTEND", datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc))
            vavail1.add("BUSYTYPE", "BUSY")
            # Manually add invalid priority to bypass icalendar validation
            vavail1["PRIORITY"] = "invalid"

            # Test out-of-range priority (> 9)
            vavail2 = Component()
            vavail2.name = "VAVAILABILITY"
            vavail2.add("DTSTART", datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc))
            vavail2.add("DTEND", datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc))
            vavail2.add("BUSYTYPE", "BUSY-UNAVAILABLE")
            vavail2.add("PRIORITY", 15)

            # Test negative priority
            vavail3 = Component()
            vavail3.name = "VAVAILABILITY"
            vavail3.add("DTSTART", datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc))
            vavail3.add("DTEND", datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
            vavail3.add("BUSYTYPE", "BUSY-TENTATIVE")
            vavail3.add("PRIORITY", -5)

            start = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
            end = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)

            periods = process_vavailability_components(
                [vavail1, vavail2, vavail3], start, end, self._tzify
            )

        # Should have warnings for all three invalid priorities (called twice each: sorting + processing)
        self.assertEqual(len(cm.output), 6)
        for output in cm.output:
            self.assertIn("Invalid PRIORITY value", output)

        # All should default to priority 0 (highest) so should appear in order
        self.assertEqual(len(periods), 3)
        self.assertEqual(periods[0][2], "BUSY")  # 9-10
        self.assertEqual(periods[1][2], "BUSY-UNAVAILABLE")  # 10-11
        self.assertEqual(periods[2][2], "BUSY-TENTATIVE")  # 11-12

    def test_available_edge_cases(self):
        """Test AVAILABLE subcomponent edge cases."""
        # VAVAILABILITY from 9-17, but AVAILABLE extends beyond
        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))
        vavail.add("BUSYTYPE", "BUSY")

        # AVAILABLE period that extends beyond parent (16:00-18:00)
        available1 = Component()
        available1.name = "AVAILABLE"
        available1.add("DTSTART", datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc))
        available1.add("DTEND", datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc))
        vavail.add_component(available1)

        # AVAILABLE period completely outside parent (7:00-8:00)
        available2 = Component()
        available2.name = "AVAILABLE"
        available2.add("DTSTART", datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc))
        available2.add("DTEND", datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc))
        vavail.add_component(available2)

        # Multiple overlapping AVAILABLE periods (10:00-12:00 and 11:00-13:00)
        available3 = Component()
        available3.name = "AVAILABLE"
        available3.add("DTSTART", datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc))
        available3.add("DTEND", datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        vavail.add_component(available3)

        available4 = Component()
        available4.name = "AVAILABLE"
        available4.add("DTSTART", datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc))
        available4.add("DTEND", datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))
        vavail.add_component(available4)

        start = datetime(2024, 1, 1, 6, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components([vavail], start, end, self._tzify)

        # Should have:
        # 1. 9:00-10:00 BUSY
        # 2. 13:00-16:00 BUSY (after the overlapping AVAILABLE periods)
        # No period for AVAILABLE outside parent range
        # AVAILABLE beyond parent is clipped to parent boundary
        self.assertEqual(len(periods), 2)
        self.assertEqual(
            periods[0],
            (
                datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                "BUSY",
            ),
        )
        self.assertEqual(
            periods[1],
            (
                datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc),
                "BUSY",
            ),
        )

    def test_missing_busytype(self):
        """Test handling of missing BUSYTYPE property."""
        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))
        # No BUSYTYPE property

        start = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components([vavail], start, end, self._tzify)

        # Should default to BUSY-UNAVAILABLE
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0][2], "BUSY-UNAVAILABLE")

    def test_complex_priority_scenarios(self):
        """Test complex priority scenarios with 3+ overlapping components."""
        # Priority 9 (lowest) - all day unavailable
        vavail1 = Component()
        vavail1.name = "VAVAILABILITY"
        vavail1.add("DTSTART", datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
        vavail1.add("DTEND", datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc))
        vavail1.add("BUSYTYPE", "BUSY-UNAVAILABLE")
        vavail1.add("PRIORITY", 9)

        # Priority 5 (medium) - working hours tentative
        vavail2 = Component()
        vavail2.name = "VAVAILABILITY"
        vavail2.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail2.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))
        vavail2.add("BUSYTYPE", "BUSY-TENTATIVE")
        vavail2.add("PRIORITY", 5)

        # Priority 3 (higher) - lunch hour busy
        vavail3 = Component()
        vavail3.name = "VAVAILABILITY"
        vavail3.add("DTSTART", datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        vavail3.add("DTEND", datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))
        vavail3.add("BUSYTYPE", "BUSY")
        vavail3.add("PRIORITY", 3)

        # Priority 1 (highest) - important meeting
        vavail4 = Component()
        vavail4.name = "VAVAILABILITY"
        vavail4.add("DTSTART", datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc))
        vavail4.add("DTEND", datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc))
        vavail4.add("BUSYTYPE", "BUSY")
        vavail4.add("PRIORITY", 1)

        start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)

        periods = process_vavailability_components(
            [vavail1, vavail2, vavail3, vavail4], start, end, self._tzify
        )

        # Expected timeline:
        # 00:00-09:00 BUSY-UNAVAILABLE (pri 9)
        # 09:00-12:00 BUSY-TENTATIVE (pri 5)
        # 12:00-13:00 BUSY (pri 3)
        # 13:00-14:00 BUSY-TENTATIVE (pri 5)
        # 14:00-15:00 BUSY (pri 1)
        # 15:00-17:00 BUSY-TENTATIVE (pri 5)
        # 17:00-24:00 BUSY-UNAVAILABLE (pri 9)
        self.assertEqual(len(periods), 7)
        self.assertEqual(periods[0][2], "BUSY-UNAVAILABLE")  # 00:00-09:00
        self.assertEqual(periods[1][2], "BUSY-TENTATIVE")  # 09:00-12:00
        self.assertEqual(periods[2][2], "BUSY")  # 12:00-13:00
        self.assertEqual(periods[3][2], "BUSY-TENTATIVE")  # 13:00-14:00
        self.assertEqual(periods[4][2], "BUSY")  # 14:00-15:00
        self.assertEqual(periods[5][2], "BUSY-TENTATIVE")  # 15:00-17:00
        self.assertEqual(periods[6][2], "BUSY-UNAVAILABLE")  # 17:00-24:00


class CalendarAvailabilityPropertyTests(unittest.TestCase):
    """Tests for CalendarAvailabilityProperty WebDAV property."""

    def test_property_name(self):
        """Test that the property has the correct name and namespace."""
        prop = CalendarAvailabilityProperty()
        self.assertEqual(
            prop.name, "{urn:ietf:params:xml:ns:caldav}calendar-availability"
        )

    def test_resource_type(self):
        """Test that the property applies to the correct resource types."""
        prop = CalendarAvailabilityProperty()
        self.assertEqual(
            prop.resource_type, (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE)
        )

    def test_not_in_allprops(self):
        """Test that the property is not included in allprop queries."""
        prop = CalendarAvailabilityProperty()
        self.assertFalse(prop.in_allprops)

    def test_get_value(self):
        """Test getting calendar availability from a resource."""
        import asyncio
        from xml.etree import ElementTree as ET

        class MockResource:
            def get_calendar_availability(self):
                return "BEGIN:VCALENDAR\nBEGIN:VAVAILABILITY\nEND:VAVAILABILITY\nEND:VCALENDAR"

        async def run_test():
            prop = CalendarAvailabilityProperty()
            el = ET.Element("test")

            await prop.get_value("/test", MockResource(), el, {})

            return el.text

        result = asyncio.run(run_test())
        self.assertEqual(
            result,
            "BEGIN:VCALENDAR\nBEGIN:VAVAILABILITY\nEND:VAVAILABILITY\nEND:VCALENDAR",
        )

    def test_set_value_with_data(self):
        """Test setting calendar availability on a resource."""
        import asyncio
        from xml.etree import ElementTree as ET

        class MockResource:
            def __init__(self):
                self.availability = None

            def set_calendar_availability(self, data):
                self.availability = data

        async def run_test():
            prop = CalendarAvailabilityProperty()
            resource = MockResource()
            el = ET.Element("test")
            el.text = (
                "BEGIN:VCALENDAR\nBEGIN:VAVAILABILITY\nEND:VAVAILABILITY\nEND:VCALENDAR"
            )

            await prop.set_value("/test", resource, el)

            return resource.availability

        result = asyncio.run(run_test())
        self.assertEqual(
            result,
            "BEGIN:VCALENDAR\nBEGIN:VAVAILABILITY\nEND:VAVAILABILITY\nEND:VCALENDAR",
        )

    def test_set_value_with_none(self):
        """Test setting calendar availability to None (removing it)."""
        import asyncio

        class MockResource:
            def __init__(self):
                self.availability = "existing data"

            def set_calendar_availability(self, data):
                self.availability = data

        async def run_test():
            prop = CalendarAvailabilityProperty()
            resource = MockResource()

            await prop.set_value("/test", resource, None)

            return resource.availability

        result = asyncio.run(run_test())
        self.assertEqual(result, None)


class CalendarQueryReporterTests(unittest.TestCase):
    """Tests for calendar-query REPORT (RFC 4791 Section 7.8)."""

    def test_report_name(self):
        """Test calendar-query reporter name."""
        from xandikos.caldav import CalendarQueryReporter

        reporter = CalendarQueryReporter()
        self.assertEqual(reporter.name, "{urn:ietf:params:xml:ns:caldav}calendar-query")

    def test_report_resource_types(self):
        """Test calendar-query supported resource types."""
        from xandikos.caldav import CalendarQueryReporter

        reporter = CalendarQueryReporter()
        self.assertEqual(
            reporter.resource_type,
            (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE),
        )


class CalendarMultigetReporterTests(unittest.TestCase):
    """Tests for calendar-multiget REPORT (RFC 4791 Section 7.9)."""

    def test_report_name(self):
        """Test calendar-multiget reporter name."""
        from xandikos.caldav import CalendarMultiGetReporter

        reporter = CalendarMultiGetReporter()
        self.assertEqual(
            reporter.name, "{urn:ietf:params:xml:ns:caldav}calendar-multiget"
        )

    def test_report_resource_types(self):
        """Test calendar-multiget supported resource types."""
        from xandikos.caldav import CalendarMultiGetReporter

        reporter = CalendarMultiGetReporter()
        self.assertEqual(
            reporter.resource_type,
            (CALENDAR_RESOURCE_TYPE, SCHEDULE_INBOX_RESOURCE_TYPE),
        )
