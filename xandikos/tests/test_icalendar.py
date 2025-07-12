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

"""Tests for xandikos.icalendar."""

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar.cal import Calendar, Event
from icalendar.prop import vCategory, vText

from xandikos import collation as _mod_collation
from xandikos.store import InvalidFileContents

from ..icalendar import (
    CalendarFilter,
    ICalendarFile,
    MissingProperty,
    TextMatcher,
    apply_time_range_vevent,
    apply_time_range_valarm,
    as_tz_aware_ts,
    expand_calendar_rrule,
    limit_calendar_recurrence_set,
    validate_calendar,
)

EXAMPLE_VCALENDAR1 = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20150314T223512Z
DTSTAMP:20150527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something
CATEGORIES:home
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""

EXAMPLE_VCALENDAR_WITH_PARAM = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED;TZID=America/Denver:20150314T223512Z
DTSTAMP:20150527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""

EXAMPLE_VCALENDAR_NO_UID = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20120314T223512Z
DTSTAMP:20130527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something without uid
END:VTODO
END:VCALENDAR
"""

EXAMPLE_VCALENDAR_INVALID_CHAR = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20150314T223512Z
DTSTAMP:20150527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something
ID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""


class ExtractCalendarUIDTests(unittest.TestCase):
    def test_extract_str(self):
        fi = ICalendarFile([EXAMPLE_VCALENDAR1], "text/calendar")
        self.assertEqual("bdc22720-b9e1-42c9-89c2-a85405d8fbff", fi.get_uid())
        fi.validate()

    def test_extract_no_uid(self):
        fi = ICalendarFile([EXAMPLE_VCALENDAR_NO_UID], "text/calendar")
        fi.validate()
        self.assertEqual(
            ["Missing required field UID"],
            list(validate_calendar(fi.calendar, strict=True)),
        )
        self.assertEqual([], list(validate_calendar(fi.calendar, strict=False)))
        self.assertRaises(KeyError, fi.get_uid)

    def test_invalid_character(self):
        fi = ICalendarFile([EXAMPLE_VCALENDAR_INVALID_CHAR], "text/calendar")
        self.assertRaises(InvalidFileContents, fi.validate)
        self.assertEqual(
            ["Invalid character b'\\\\x0c' in field SUMMARY"],
            list(validate_calendar(fi.calendar, strict=False)),
        )


class CalendarFilterTests(unittest.TestCase):
    def setUp(self):
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR1], "text/calendar")

    def test_simple_comp_filter(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent("VEVENT")
        self.assertEqual(filter.index_keys(), [["C=VCALENDAR/C=VEVENT"]])
        self.assertEqual(
            self.cal.get_indexes(["C=VCALENDAR/C=VEVENT", "C=VCALENDAR/C=VTODO"]),
            {"C=VCALENDAR/C=VEVENT": [], "C=VCALENDAR/C=VTODO": [True]},
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {"C=VCALENDAR/C=VEVENT": [], "C=VCALENDAR/C=VTODO": [True]},
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent("VTODO")
        self.assertTrue(filter.check("file", self.cal))
        self.assertTrue(
            filter.check_from_indexes(
                "file",
                {"C=VCALENDAR/C=VEVENT": [], "C=VCALENDAR/C=VTODO": [True]},
            )
        )

    def test_simple_comp_missing_filter(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO", is_not_defined=True
        )
        self.assertEqual(
            filter.index_keys(), [["C=VCALENDAR/C=VTODO"], ["C=VCALENDAR"]]
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR": [True],
                    "C=VCALENDAR/C=VEVENT": [],
                    "C=VCALENDAR/C=VTODO": [True],
                },
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT", is_not_defined=True
        )
        self.assertTrue(filter.check("file", self.cal))
        self.assertTrue(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR": [True],
                    "C=VCALENDAR/C=VEVENT": [],
                    "C=VCALENDAR/C=VTODO": [True],
                },
            )
        )

    def test_prop_presence_filter(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("X-SUMMARY")
        self.assertEqual(filter.index_keys(), [["C=VCALENDAR/C=VTODO/P=X-SUMMARY"]])
        self.assertFalse(
            filter.check_from_indexes("file", {"C=VCALENDAR/C=VTODO/P=X-SUMMARY": []})
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("SUMMARY")
        self.assertTrue(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=SUMMARY": [b"do something"]}
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def test_prop_explicitly_missing_filter(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_property("X-SUMMARY", is_not_defined=True)
        self.assertEqual(
            filter.index_keys(),
            [["C=VCALENDAR/C=VEVENT/P=X-SUMMARY"], ["C=VCALENDAR/C=VEVENT"]],
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VEVENT/P=X-SUMMARY": [],
                    "C=VCALENDAR/C=VEVENT": [],
                },
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("X-SUMMARY", is_not_defined=True)
        self.assertTrue(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VTODO/P=X-SUMMARY": [],
                    "C=VCALENDAR/C=VTODO": [True],
                },
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def test_prop_text_match(self):
        filter = CalendarFilter(None)
        f = filter.filter_subcomponent("VCALENDAR")
        f = f.filter_subcomponent("VTODO")
        f = f.filter_property("SUMMARY")
        f.filter_text_match("do something different")
        self.assertEqual(filter.index_keys(), [["C=VCALENDAR/C=VTODO/P=SUMMARY"]])
        self.assertFalse(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=SUMMARY": [b"do something"]}
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("SUMMARY").filter_text_match("do something")
        self.assertTrue(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=SUMMARY": [b"do something"]}
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def test_prop_text_match_category(self):
        filter = CalendarFilter(None)
        f = filter.filter_subcomponent("VCALENDAR")
        f = f.filter_subcomponent("VTODO")
        f = f.filter_property("CATEGORIES")
        f.filter_text_match("work")
        self.assertEqual(
            self.cal.get_indexes(["C=VCALENDAR/C=VTODO/P=CATEGORIES"]),
            {"C=VCALENDAR/C=VTODO/P=CATEGORIES": [b"home"]},
        )

        self.assertEqual(filter.index_keys(), [["C=VCALENDAR/C=VTODO/P=CATEGORIES"]])
        self.assertFalse(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=CATEGORIES": [b"home"]}
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("CATEGORIES").filter_text_match("home")
        self.assertTrue(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=CATEGORIES": [b"home"]}
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def test_param_text_match(self):
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_WITH_PARAM], "text/calendar")
        filter = CalendarFilter(None)
        f = filter.filter_subcomponent("VCALENDAR")
        f = f.filter_subcomponent("VTODO")
        f = f.filter_property("CREATED")
        f = f.filter_parameter("TZID")
        f.filter_text_match("America/Blah")
        self.assertEqual(
            filter.index_keys(),
            [
                ["C=VCALENDAR/C=VTODO/P=CREATED/A=TZID"],
                ["C=VCALENDAR/C=VTODO/P=CREATED"],
            ],
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {"C=VCALENDAR/C=VTODO/P=CREATED/A=TZID": [b"America/Denver"]},
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(None)
        f = filter.filter_subcomponent("VCALENDAR")
        f = f.filter_subcomponent("VTODO")
        f = f.filter_property("CREATED")
        f = f.filter_parameter("TZID")
        f.filter_text_match("America/Denver")
        self.assertTrue(
            filter.check_from_indexes(
                "file",
                {"C=VCALENDAR/C=VTODO/P=CREATED/A=TZID": [b"America/Denver"]},
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def _tzify(self, dt):
        return as_tz_aware_ts(dt, ZoneInfo("UTC"))

    def test_prop_apply_time_range(self):
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("CREATED").filter_time_range(
            self._tzify(datetime(2019, 3, 10, 22, 35, 12)),
            self._tzify(datetime(2019, 3, 18, 22, 35, 12)),
        )
        self.assertEqual(filter.index_keys(), [["C=VCALENDAR/C=VTODO/P=CREATED"]])
        self.assertFalse(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314T223512Z"]}
            )
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314"]}
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(self._tzify)
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_property("CREATED").filter_time_range(
            self._tzify(datetime(2015, 3, 10, 22, 35, 12)),
            self._tzify(datetime(2015, 3, 18, 22, 35, 12)),
        )
        self.assertTrue(
            filter.check_from_indexes(
                "file", {"C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314T223512Z"]}
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def test_comp_apply_time_range(self):
        self.assertEqual(
            self.cal.get_indexes(["C=VCALENDAR/C=VTODO/P=CREATED"]),
            {"C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314T223512Z"]},
        )

        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_time_range(
            self._tzify(datetime(2015, 3, 3, 22, 35, 12)),
            self._tzify(datetime(2015, 3, 10, 22, 35, 12)),
        )
        self.assertEqual(
            filter.index_keys(),
            [
                ["C=VCALENDAR/C=VTODO/P=DTSTART"],
                ["C=VCALENDAR/C=VTODO/P=DUE"],
                ["C=VCALENDAR/C=VTODO/P=DURATION"],
                ["C=VCALENDAR/C=VTODO/P=CREATED"],
                ["C=VCALENDAR/C=VTODO/P=COMPLETED"],
                ["C=VCALENDAR/C=VTODO"],
            ],
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314T223512Z"],
                    "C=VCALENDAR/C=VTODO": [True],
                    "C=VCALENDAR/C=VTODO/P=DUE": [],
                    "C=VCALENDAR/C=VTODO/P=DURATION": [],
                    "C=VCALENDAR/C=VTODO/P=COMPLETED": [],
                    "C=VCALENDAR/C=VTODO/P=DTSTART": [],
                },
            )
        )
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314"],
                    "C=VCALENDAR/C=VTODO": [True],
                    "C=VCALENDAR/C=VTODO/P=DUE": [],
                    "C=VCALENDAR/C=VTODO/P=DURATION": [],
                    "C=VCALENDAR/C=VTODO/P=COMPLETED": [],
                    "C=VCALENDAR/C=VTODO/P=DTSTART": [],
                },
            )
        )
        self.assertFalse(filter.check("file", self.cal))
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_time_range(
            self._tzify(datetime(2015, 3, 10, 22, 35, 12)),
            self._tzify(datetime(2015, 3, 18, 22, 35, 12)),
        )
        self.assertTrue(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VTODO/P=CREATED": [b"20150314T223512Z"],
                    "C=VCALENDAR/C=VTODO": [True],
                    "C=VCALENDAR/C=VTODO/P=DUE": [],
                    "C=VCALENDAR/C=VTODO/P=DURATION": [],
                    "C=VCALENDAR/C=VTODO/P=COMPLETED": [],
                    "C=VCALENDAR/C=VTODO/P=DTSTART": [],
                },
            )
        )
        self.assertTrue(filter.check("file", self.cal))


class TextMatchTest(unittest.TestCase):
    def test_default_collation(self):
        tm = TextMatcher("summary", "foobar")
        self.assertTrue(tm.match(vText("FOOBAR")))
        self.assertTrue(tm.match(vText("foobar")))
        self.assertFalse(tm.match(vText("fobar")))
        self.assertTrue(tm.match_indexes({None: [b"foobar"]}))
        self.assertTrue(tm.match_indexes({None: [b"FOOBAR"]}))
        self.assertFalse(tm.match_indexes({None: [b"fobar"]}))

    def test_casecmp_collation(self):
        tm = TextMatcher("summary", "foobar", collation="i;ascii-casemap")
        self.assertTrue(tm.match(vText("FOOBAR")))
        self.assertTrue(tm.match(vText("foobar")))
        self.assertFalse(tm.match(vText("fobar")))
        self.assertTrue(tm.match_indexes({None: [b"foobar"]}))
        self.assertTrue(tm.match_indexes({None: [b"FOOBAR"]}))
        self.assertFalse(tm.match_indexes({None: [b"fobar"]}))

    def test_cmp_collation(self):
        tm = TextMatcher("summary", "foobar", collation="i;octet")
        self.assertFalse(tm.match(vText("FOOBAR")))
        self.assertTrue(tm.match(vText("foobar")))
        self.assertFalse(tm.match(vText("fobar")))
        self.assertFalse(tm.match_indexes({None: [b"FOOBAR"]}))
        self.assertTrue(tm.match_indexes({None: [b"foobar"]}))
        self.assertFalse(tm.match_indexes({None: [b"fobar"]}))

    def test_category(self):
        tm = TextMatcher("categories", "foobar")
        self.assertTrue(tm.match(vCategory(["FOOBAR", "blah"])))
        self.assertTrue(tm.match(vCategory(["foobar"])))
        self.assertFalse(tm.match(vCategory(["fobar"])))
        self.assertTrue(tm.match_indexes({None: [b"foobar,blah"]}))
        self.assertFalse(tm.match_indexes({None: [b"foobarblah"]}))

    def test_unknown_type(self):
        tm = TextMatcher("dontknow", "foobar")
        self.assertFalse(tm.match(object()))
        self.assertFalse(tm.match_indexes({None: [b"foobarblah"]}))

    def test_unknown_collation(self):
        self.assertRaises(
            _mod_collation.UnknownCollation,
            TextMatcher,
            "summary",
            "foobar",
            collation="i;blah",
        )


class ApplyTimeRangeVeventTests(unittest.TestCase):
    def _tzify(self, dt):
        return as_tz_aware_ts(dt, ZoneInfo("UTC"))

    def test_missing_dtstart(self):
        ev = Event()
        self.assertRaises(
            MissingProperty,
            apply_time_range_vevent,
            datetime.utcnow(),
            datetime.utcnow(),
            ev,
            self._tzify,
        )


class ExpandCalendarRRuleTests(unittest.TestCase):
    def test_expand_recurring_date_only_with_exception(self):
        """Test expansion of recurring events with date-only values and exceptions.

        This test reproduces issue #365 where expanding recurring all-day events
        with exceptions would fail due to date vs datetime type mismatch.
        """
        from icalendar import Calendar

        # Create a calendar with a bi-weekly recurring event and an exception
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-recurring-event@example.com
DTSTART;VALUE=DATE:20240101
SUMMARY:Bi-weekly event
RRULE:FREQ=WEEKLY;INTERVAL=2
END:VEVENT
BEGIN:VEVENT
UID:test-recurring-event@example.com
RECURRENCE-ID;VALUE=DATE:20240115
DTSTART;VALUE=DATE:20240116
SUMMARY:Bi-weekly event (moved)
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Expand the calendar
        start = datetime(2024, 1, 1)
        end = datetime(2024, 2, 1)

        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 3)  # Jan 1, Jan 15 (moved to 16), Jan 29

        # Check that the exception was properly handled
        dates = sorted([ev["DTSTART"].dt for ev in events])
        from datetime import date

        expected_dates = [
            date(2024, 1, 1),
            date(2024, 1, 16),  # Moved from Jan 15
            date(2024, 1, 29),
        ]
        self.assertEqual(dates, expected_dates)

    def test_expand_preserves_vtimezone(self):
        """Test that VTIMEZONE components are preserved during expansion."""
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTIMEZONE
TZID:Europe/London
BEGIN:STANDARD
DTSTART:20231029T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20240331T010000
TZOFFSETFROM:+0000
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:tz-test@example.com
DTSTART;TZID=Europe/London:20240115T100000
DTEND;TZID=Europe/London:20240115T110000
SUMMARY:Meeting
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)
        # Use timezone-aware datetimes for start/end
        start = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 2, 1, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)

        # Check VTIMEZONE is preserved
        timezones = [comp for comp in expanded.walk() if comp.name == "VTIMEZONE"]
        self.assertEqual(len(timezones), 1)
        self.assertEqual(timezones[0]["TZID"], "Europe/London")

        # Check events still reference the timezone
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 3)
        for event in events:
            # Check that DTSTART has timezone parameter
            self.assertIn("TZID", event["DTSTART"].params)

    def test_expand_boundary_conditions(self):
        """Test expansion at exact boundaries of the time range."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:boundary-test@example.com
DTSTART:20240115T100000Z
DTEND:20240115T110000Z
SUMMARY:Boundary Event
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Test with event exactly at start boundary
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 18, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 3)

        # Test with event exactly at end boundary
        start = datetime(2024, 1, 15, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 16, 10, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        # Should include only event on 15th (16th is at boundary and may or may not be included)
        self.assertGreaterEqual(len(events), 1)
        self.assertLessEqual(len(events), 2)


class LimitCalendarRecurrenceSetTests(unittest.TestCase):
    def test_limit_recurrence_set_basic(self):
        """Test basic functionality of limit_calendar_recurrence_set."""
        from icalendar import Calendar
        from datetime import timezone

        # Create a calendar with a recurring event and some overrides
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-recurring@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
SUMMARY:Weekly Meeting
RRULE:FREQ=WEEKLY
END:VEVENT
BEGIN:VEVENT
UID:test-recurring@example.com
RECURRENCE-ID:20240115T100000Z
DTSTART:20240115T140000Z
DTEND:20240115T150000Z
SUMMARY:Weekly Meeting (moved to afternoon)
END:VEVENT
BEGIN:VEVENT
UID:test-recurring@example.com
RECURRENCE-ID:20240301T100000Z
DTSTART:20240301T100000Z
DTEND:20240301T110000Z
SUMMARY:Weekly Meeting (March override)
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Limit to January 2024
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 2, 1, tzinfo=timezone.utc)

        limited = limit_calendar_recurrence_set(cal, start, end)

        events = [comp for comp in limited.walk() if comp.name == "VEVENT"]
        # Should have: master component + January override (March override excluded)
        self.assertEqual(len(events), 2)

        # Check we have the master component
        has_master = any(ev for ev in events if "RECURRENCE-ID" not in ev)
        self.assertTrue(has_master)

        # Check we have the January override but not March
        overrides = [ev for ev in events if "RECURRENCE-ID" in ev]
        self.assertEqual(len(overrides), 1)
        self.assertEqual(
            overrides[0]["RECURRENCE-ID"].dt,
            datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        )

    def test_limit_recurrence_set_thisandfuture(self):
        """Test handling of THISANDFUTURE modifications."""
        from icalendar import Calendar
        from datetime import timezone

        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-recurring@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
SUMMARY:Daily Meeting
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:test-recurring@example.com
RECURRENCE-ID;RANGE=THISANDFUTURE:20240215T100000Z
DTSTART:20240215T140000Z
DTEND:20240215T150000Z
SUMMARY:Daily Meeting (time changed from Feb 15 onwards)
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Query for January - should not include the THISANDFUTURE modification
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 2, 1, tzinfo=timezone.utc)

        limited = limit_calendar_recurrence_set(cal, start, end)
        events = [comp for comp in limited.walk() if comp.name == "VEVENT"]
        # Should only have master component
        self.assertEqual(len(events), 1)
        self.assertNotIn("RECURRENCE-ID", events[0])

        # Query for February - should include the THISANDFUTURE modification
        start = datetime(2024, 2, 1, tzinfo=timezone.utc)
        end = datetime(2024, 3, 1, tzinfo=timezone.utc)

        limited = limit_calendar_recurrence_set(cal, start, end)
        events = [comp for comp in limited.walk() if comp.name == "VEVENT"]
        # Should have master component + THISANDFUTURE override
        self.assertEqual(len(events), 2)

    def test_limit_recurrence_set_date_values(self):
        """Test handling of date-only (all-day) events."""
        from icalendar import Calendar
        from datetime import date, timezone

        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-allday@example.com
DTSTART;VALUE=DATE:20240101
SUMMARY:All-day recurring event
RRULE:FREQ=MONTHLY;BYMONTHDAY=1
END:VEVENT
BEGIN:VEVENT
UID:test-allday@example.com
RECURRENCE-ID;VALUE=DATE:20240201
DTSTART;VALUE=DATE:20240202
SUMMARY:All-day recurring event (moved)
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Query for February
        start = datetime(2024, 2, 1, tzinfo=timezone.utc)
        end = datetime(2024, 3, 1, tzinfo=timezone.utc)

        limited = limit_calendar_recurrence_set(cal, start, end)
        events = [comp for comp in limited.walk() if comp.name == "VEVENT"]
        # Should have master + February override
        self.assertEqual(len(events), 2)

        # Verify the override is included
        overrides = [ev for ev in events if "RECURRENCE-ID" in ev]
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0]["RECURRENCE-ID"].dt, date(2024, 2, 1))


class ApplyTimeRangeValarmTests(unittest.TestCase):
    def _tzify(self, dt):
        return as_tz_aware_ts(dt, ZoneInfo("UTC"))

    def test_relative_trigger_from_start(self):
        """Test VALARM with relative trigger from DTSTART."""
        from icalendar import Calendar, Event, Alarm
        from icalendar.prop import vDuration
        from ..icalendar import _create_enriched_valarm

        cal = Calendar()
        event = Event()
        event.add("dtstart", datetime(2024, 1, 15, 10, 0, 0))
        event.add("summary", "Test Event")

        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add(
            "trigger", vDuration(timedelta(minutes=-15))
        )  # 15 minutes before start
        alarm.add("description", "Event reminder")

        event.add_component(alarm)
        cal.add_component(event)

        # Create enriched alarm
        enriched_alarm = _create_enriched_valarm(alarm, event)

        # Time range includes the trigger time (9:45)
        start = self._tzify(datetime(2024, 1, 15, 9, 30, 0))
        end = self._tzify(datetime(2024, 1, 15, 10, 0, 0))

        self.assertTrue(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )

        # Time range does not include the trigger time
        start = self._tzify(datetime(2024, 1, 15, 10, 0, 0))
        end = self._tzify(datetime(2024, 1, 15, 11, 0, 0))

        self.assertFalse(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )

    def test_relative_trigger_from_end(self):
        """Test VALARM with relative trigger from DTEND."""
        from icalendar import Calendar, Event, Alarm
        from icalendar.prop import vDuration
        from ..icalendar import _create_enriched_valarm

        cal = Calendar()
        event = Event()
        event.add("dtstart", datetime(2024, 1, 15, 10, 0, 0))
        event.add("dtend", datetime(2024, 1, 15, 11, 0, 0))
        event.add("summary", "Test Event")

        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        trigger = vDuration(timedelta(minutes=-5))  # 5 minutes before end
        trigger.params["RELATED"] = "END"
        alarm.add("trigger", trigger)
        alarm.add("description", "Event reminder")

        event.add_component(alarm)
        cal.add_component(event)

        # Create enriched alarm
        enriched_alarm = _create_enriched_valarm(alarm, event)

        # Time range includes the trigger time (10:55)
        start = self._tzify(datetime(2024, 1, 15, 10, 50, 0))
        end = self._tzify(datetime(2024, 1, 15, 11, 0, 0))

        self.assertTrue(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )

    def test_absolute_trigger(self):
        """Test VALARM with absolute trigger time."""
        from icalendar import Calendar, Event, Alarm
        from icalendar.prop import vDDDTypes
        from ..icalendar import _create_enriched_valarm

        cal = Calendar()
        event = Event()
        event.add("dtstart", datetime(2024, 1, 15, 10, 0, 0))
        event.add("summary", "Test Event")

        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("trigger", vDDDTypes(datetime(2024, 1, 15, 9, 30, 0)))
        alarm.add("description", "Event reminder")

        event.add_component(alarm)
        cal.add_component(event)

        # Create enriched alarm (for absolute triggers, it's unchanged)
        enriched_alarm = _create_enriched_valarm(alarm, event)

        # Time range includes the trigger time
        start = self._tzify(datetime(2024, 1, 15, 9, 0, 0))
        end = self._tzify(datetime(2024, 1, 15, 10, 0, 0))

        self.assertTrue(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )

    def test_repeating_alarm(self):
        """Test VALARM with repeat and duration."""
        from icalendar import Calendar, Event, Alarm
        from icalendar.prop import vDuration
        from ..icalendar import _create_enriched_valarm

        cal = Calendar()
        event = Event()
        event.add("dtstart", datetime(2024, 1, 15, 10, 0, 0))
        event.add("summary", "Test Event")

        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add(
            "trigger", vDuration(timedelta(minutes=-30))
        )  # 30 minutes before start
        alarm.add("duration", vDuration(timedelta(minutes=5)))  # 5 minute intervals
        alarm.add("repeat", 3)  # Repeat 3 times
        alarm.add("description", "Event reminder")

        event.add_component(alarm)
        cal.add_component(event)

        # Create enriched alarm
        enriched_alarm = _create_enriched_valarm(alarm, event)

        # Time range includes one of the repetitions (9:40 - second repeat)
        start = self._tzify(datetime(2024, 1, 15, 9, 35, 0))
        end = self._tzify(datetime(2024, 1, 15, 9, 45, 0))

        self.assertTrue(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )

    def test_todo_alarm(self):
        """Test VALARM on VTODO with DUE."""
        from icalendar import Calendar, Todo, Alarm
        from icalendar.prop import vDuration
        from ..icalendar import _create_enriched_valarm

        cal = Calendar()
        todo = Todo()
        todo.add("dtstart", datetime(2024, 1, 15, 9, 0, 0))
        todo.add("due", datetime(2024, 1, 15, 17, 0, 0))
        todo.add("summary", "Test Task")

        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        trigger = vDuration(timedelta(hours=-1))  # 1 hour before due
        trigger.params["RELATED"] = "END"
        alarm.add("trigger", trigger)
        alarm.add("description", "Task reminder")

        todo.add_component(alarm)
        cal.add_component(todo)

        # Create enriched alarm
        enriched_alarm = _create_enriched_valarm(alarm, todo)

        # Time range includes the trigger time (16:00)
        start = self._tzify(datetime(2024, 1, 15, 15, 30, 0))
        end = self._tzify(datetime(2024, 1, 15, 16, 30, 0))

        self.assertTrue(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )

    def test_no_trigger(self):
        """Test VALARM without TRIGGER property."""
        from icalendar import Calendar, Event, Alarm
        from ..icalendar import _create_enriched_valarm

        cal = Calendar()
        event = Event()
        event.add("dtstart", datetime(2024, 1, 15, 10, 0, 0))
        event.add("summary", "Test Event")

        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", "Event reminder")
        # No trigger property

        event.add_component(alarm)
        cal.add_component(event)

        # Create enriched alarm (no change without trigger)
        enriched_alarm = _create_enriched_valarm(alarm, event)

        start = self._tzify(datetime(2024, 1, 15, 9, 0, 0))
        end = self._tzify(datetime(2024, 1, 15, 11, 0, 0))

        self.assertFalse(
            apply_time_range_valarm(start, end, enriched_alarm, self._tzify)
        )
