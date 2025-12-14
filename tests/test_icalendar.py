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
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar.cal import Calendar, Event, Alarm, Todo
from icalendar.prop import vCategory, vText, vDuration, vDDDTypes

from xandikos import collation as _mod_collation
from xandikos.store import InvalidFileContents

from xandikos.icalendar import (
    CalendarFilter,
    ICalendarFile,
    MissingProperty,
    TextMatcher,
    _create_enriched_valarm,
    _event_overlaps_range,
    apply_time_range_vevent,
    apply_time_range_valarm,
    apply_time_range_vavailability,
    apply_time_range_available,
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

EXAMPLE_VCALENDAR_RRULE = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VEVENT
DTSTART:20150527T221952Z
DURATION:P1D
RRULE:FREQ=YEARLY;UNTIL=20180314T223512Z
LAST-MODIFIED:20150314T223512Z
SUMMARY:do something
CATEGORIES:home
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VEVENT
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

    def test_escaped_newlines_allowed(self):
        # Test that properly escaped \n and \r sequences are allowed
        # This is critical for calendar invites from email clients like Thunderbird
        cal_data = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-multiline@example.com
DTSTART:20250101T120000Z
SUMMARY:Event with description
DESCRIPTION:Line 1\\nLine 2\\r\\nLine 3
END:VEVENT
END:VCALENDAR
"""
        fi = ICalendarFile([cal_data], "text/calendar")
        # Should validate successfully (no exception raised)
        fi.validate()
        # Should have no validation errors
        self.assertEqual([], list(validate_calendar(fi.calendar, strict=False)))


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
        filter = CalendarFilter(ZoneInfo("UTC"))
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
        # With proper index-based filtering, this VTODO should NOT match the time range
        # because CREATED (March 14) is after the time range end (March 10)
        # According to RFC 4791: for VTODO with only CREATED, condition is end >= created.dt
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
        # Same logic applies for date-only CREATED value
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

    def test_comp_apply_time_range_rrule(self):
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # With the new approach, indexes contain only original event data
        # RRULE expansion happens at query time in match_indexes()
        indexes = self.cal.get_indexes(
            ["C=VCALENDAR/C=VEVENT/P=DTSTART", "C=VCALENDAR/C=VEVENT/P=RRULE"]
        )
        dtstart_values = indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"]
        rrule_values = indexes["C=VCALENDAR/C=VEVENT/P=RRULE"]

        # Should contain only the original event in indexes
        self.assertEqual(len(dtstart_values), 1)
        self.assertEqual(dtstart_values[0], b"20150527T221952Z")

        # Should have RRULE information for expansion at query time
        self.assertEqual(len(rrule_values), 1)
        self.assertEqual(rrule_values[0], b"FREQ=YEARLY;UNTIL=20180314T223512Z")

        # DURATION doesn't need expansion since it's the same for all instances
        self.assertEqual(
            self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DURATION"]),
            {"C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D"]},
        )

        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2015, 3, 3, 22, 35, 12)),
            end=self._tzify(datetime(2016, 3, 10, 22, 35, 12)),
        )
        self.assertEqual(
            filter.index_keys(),
            [
                ["C=VCALENDAR/C=VEVENT/P=DTSTART"],
                ["C=VCALENDAR/C=VEVENT/P=DTEND"],
                ["C=VCALENDAR/C=VEVENT/P=DURATION"],
                ["C=VCALENDAR/C=VEVENT/P=RRULE"],
                ["C=VCALENDAR/C=VEVENT"],
            ],
        )
        # With proper index-based filtering, this should return False
        # because DTSTART (2014-03-14) is before the time range (2015-03 to 2016-03)
        self.assertFalse(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20140314T223512Z"],
                    "C=VCALENDAR/C=VEVENT": [True],
                    "C=VCALENDAR/C=VEVENT/P=DTEND": [],
                    "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D"],
                },
            )
        )
        self.assertTrue(filter.check("file", self.cal))
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            self._tzify(datetime(2016, 3, 10, 22, 35, 12)),
            self._tzify(datetime(2017, 3, 18, 22, 35, 12)),
        )
        self.assertTrue(
            filter.check_from_indexes(
                "file",
                {
                    "C=VCALENDAR/C=VEVENT/P=DTSTART": [
                        b"20150527T221952Z",
                        b"20160527T221952Z",
                        b"20170527T221952Z",
                    ],
                    "C=VCALENDAR/C=VEVENT/P=DTEND": [],
                    "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D", b"P1D", b"P1D"],
                    "C=VCALENDAR/C=VEVENT": True,
                },
            )
        )
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_exact_match(self):
        """Test that rrule filtering works correctly when one recurrence exactly matches the time range."""
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # Filter for a time range that should match the second occurrence (2016)
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self._tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        # Test with indexes - should match because 2016-05-27 falls within range
        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [
                b"20150527T221952Z",
                b"20160527T221952Z",
                b"20170527T221952Z",
            ],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D", b"P1D", b"P1D"],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))

        # Also test with the actual calendar
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_no_match(self):
        """Test that rrule filtering correctly returns False when no recurrences match."""
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # Filter for a time range that should not match any occurrences
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2014, 1, 1, 0, 0, 0)),
            end=self._tzify(datetime(2014, 12, 31, 0, 0, 0)),
        )

        # With the new approach, RRULE expansion determines the correct result from indexes
        # Indexes contain only original events and RRULE, not expanded ones
        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20150527T221952Z"],  # Only original
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=RRULE": [b"FREQ=YEARLY;UNTIL=20180314T223512Z"],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D"],  # Only original
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertFalse(filter.check_from_indexes("file", indexes))

        # Also test with the actual calendar
        self.assertFalse(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_partial_overlap(self):
        """Test rrule filtering when time range partially overlaps with events."""
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # Filter for a time range that overlaps with the event duration (P1D = 1 day)
        # Event starts 2015-05-27 22:19:52Z and lasts 1 day
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2015, 5, 28, 12, 0, 0)),  # During the event
            end=self._tzify(datetime(2015, 5, 29, 12, 0, 0)),  # After the event
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [
                b"20150527T221952Z",
                b"20160527T221952Z",
                b"20170527T221952Z",
            ],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D", b"P1D", b"P1D"],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_multiple_matches(self):
        """Test rrule filtering when multiple recurrences match the time range."""
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # Filter for a wide time range that includes multiple occurrences
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2015, 1, 1, 0, 0, 0)),
            end=self._tzify(datetime(2017, 12, 31, 0, 0, 0)),
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [
                b"20150527T221952Z",
                b"20160527T221952Z",
                b"20170527T221952Z",
            ],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D", b"P1D", b"P1D"],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_edge_case_boundaries(self):
        """Test rrule filtering with boundary conditions."""
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # Test exact start time boundary
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 27, 22, 19, 52)),  # Exact start time
            end=self._tzify(datetime(2016, 5, 27, 22, 19, 53)),  # One second later
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [
                b"20150527T221952Z",
                b"20160527T221952Z",
                b"20170527T221952Z",
            ],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D", b"P1D", b"P1D"],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_with_dtend(self):
        """Test rrule filtering with events that have DTEND instead of DURATION."""
        # Create a test calendar with DTEND instead of DURATION
        rrule_with_dtend = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20150527T100000Z
DTEND:20150527T120000Z
RRULE:FREQ=YEARLY;COUNT=3
SUMMARY:Test event with DTEND
UID:test-dtend@example.com
END:VEVENT
END:VCALENDAR
"""
        self.cal = ICalendarFile([rrule_with_dtend], "text/calendar")

        # Check that indexes are generated correctly
        dtstart_indexes = self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DTSTART"])
        dtend_indexes = self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DTEND"])

        # With the new approach, indexes contain only original events, not expanded instances
        expected_dtstart = [b"20150527T100000Z"]  # Only the original event
        expected_dtend = [b"20150527T120000Z"]  # Only the original end time

        self.assertEqual(
            dtstart_indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"], expected_dtstart
        )
        self.assertEqual(dtend_indexes["C=VCALENDAR/C=VEVENT/P=DTEND"], expected_dtend)

        # Test filtering
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 27, 11, 0, 0)),  # During the event
            end=self._tzify(datetime(2016, 5, 27, 11, 30, 0)),
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": expected_dtstart,
            "C=VCALENDAR/C=VEVENT/P=DTEND": expected_dtend,
            "C=VCALENDAR/C=VEVENT/P=RRULE": [b"FREQ=YEARLY;COUNT=3"],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_with_exceptions(self):
        """Test rrule filtering with recurring events that have exception instances."""
        # Create a calendar with a recurring event and an exception
        rrule_with_exception = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20150527T100000Z
DTEND:20150527T120000Z
RRULE:FREQ=YEARLY;COUNT=3
SUMMARY:Recurring event
UID:test-exception@example.com
END:VEVENT
BEGIN:VEVENT
DTSTART:20160527T140000Z
DTEND:20160527T160000Z
RECURRENCE-ID:20160527T100000Z
SUMMARY:Exception event (moved)
UID:test-exception@example.com
END:VEVENT
END:VCALENDAR
"""
        self.cal = ICalendarFile([rrule_with_exception], "text/calendar")

        # The expanded calendar should have the exception replacement
        dtstart_indexes = self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DTSTART"])
        dtend_indexes = self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DTEND"])

        # With the new approach, indexes contain only original components (no expansion)
        # This calendar has 2 VEVENT components: the recurring one and the exception one
        expected_dtstart = [
            b"20150527T100000Z",  # Original recurring event
            b"20160527T140000Z",  # Exception event (separate component)
        ]
        expected_dtend = [
            b"20150527T120000Z",  # Original recurring event end
            b"20160527T160000Z",  # Exception event end
        ]

        self.assertEqual(
            dtstart_indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"], expected_dtstart
        )
        self.assertEqual(dtend_indexes["C=VCALENDAR/C=VEVENT/P=DTEND"], expected_dtend)

        # Test filtering for the moved event time
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 27, 14, 30, 0)),  # During moved event
            end=self._tzify(datetime(2016, 5, 27, 15, 30, 0)),
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": expected_dtstart,
            "C=VCALENDAR/C=VEVENT/P=DTEND": expected_dtend,
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_date_only_events(self):
        """Test rrule filtering with all-day (date-only) recurring events."""
        # Create a calendar with date-only recurring events
        rrule_date_only = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART;VALUE=DATE:20150527
RRULE:FREQ=YEARLY;COUNT=3
SUMMARY:All-day recurring event
UID:test-date-only@example.com
END:VEVENT
END:VCALENDAR
"""
        self.cal = ICalendarFile([rrule_date_only], "text/calendar")

        # Check indexes are generated correctly for date-only events
        # With the new approach, indexes contain only the original event (no expansion)
        dtstart_indexes = self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DTSTART"])
        expected_dtstart = [b"20150527"]  # Only the original event

        self.assertEqual(
            dtstart_indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"], expected_dtstart
        )

        # Test filtering - should match when date falls within range
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self._tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": expected_dtstart,
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=RRULE": [b"FREQ=YEARLY;COUNT=3"],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_complex_rrule(self):
        """Test rrule filtering with more complex recurrence rules."""
        # Create a calendar with a weekly recurring event
        rrule_weekly = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20150527T100000Z
DTEND:20150527T110000Z
RRULE:FREQ=WEEKLY;COUNT=5;BYDAY=WE
SUMMARY:Weekly meeting
UID:test-weekly@example.com
END:VEVENT
END:VCALENDAR
"""
        self.cal = ICalendarFile([rrule_weekly], "text/calendar")

        # Check that weekly recurrences are generated correctly
        dtstart_indexes = self.cal.get_indexes(["C=VCALENDAR/C=VEVENT/P=DTSTART"])

        # With the new approach, indexes contain only the original event (no expansion)
        expected_dtstart = [
            b"20150527T100000Z",  # Only the original event
        ]

        self.assertEqual(
            dtstart_indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"], expected_dtstart
        )

        # Test filtering for a specific week
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2015, 6, 2, 0, 0, 0)),  # Tuesday before week 2
            end=self._tzify(datetime(2015, 6, 4, 0, 0, 0)),  # Thursday after week 2
        )

        indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": expected_dtstart,
            "C=VCALENDAR/C=VEVENT/P=DTEND": [
                b"20150527T110000Z"
            ],  # Only original event
            "C=VCALENDAR/C=VEVENT/P=RRULE": [b"FREQ=WEEKLY;COUNT=5;BYDAY=WE"],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }
        self.assertTrue(filter.check_from_indexes("file", indexes))
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_empty_indexes(self):
        """Test rrule filtering behavior with empty or incomplete indexes."""
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR_RRULE], "text/calendar")

        # Test with completely empty indexes
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self._tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        # With the new approach, insufficient index data raises an exception
        empty_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }
        from xandikos.store import InsufficientIndexDataError

        with self.assertRaises(InsufficientIndexDataError):
            filter.check_from_indexes("file", empty_indexes)

        # Test with partial indexes (missing component marker)
        missing_component_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20160527T221952Z"],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D"],
            # Missing "C=VCALENDAR/C=VEVENT": True
        }
        # Missing component marker should also raise an exception
        with self.assertRaises(InsufficientIndexDataError):
            filter.check_from_indexes("file", missing_component_indexes)

        # Verify that the full file check still works correctly
        self.assertTrue(filter.check("file", self.cal))

    def test_rrule_index_based_filtering_mixed_types(self):
        """Test rrule filtering with mixed datetime and date types in indexes."""
        # Test with inconsistent data types (should handle gracefully)
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self._tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        # Mix of datetime and date formats (unusual but should not crash)
        mixed_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [
                b"20150527T221952Z",  # datetime
                b"20160527",  # date
                b"20170527T221952Z",  # datetime
            ],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [b"P1D", b"P1D", b"P1D"],
            "C=VCALENDAR/C=VEVENT": True,
        }

        # Should handle mixed types gracefully and still find matches
        self.assertTrue(filter.check_from_indexes("file", mixed_indexes))

    def test_unbounded_query_no_infinite_expansion(self):
        """Test that unbounded queries don't infinitely expand recurring VTODOs.

        This test reproduces the pycaldav testTodoDatesearch failure where
        xandikos was returning too many todos due to infinite expansion of
        yearly recurring events in unbounded CalDAV queries.
        """
        # Create a calendar with a yearly recurring VTODO
        yearly_vtodo = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTODO
UID:yearly-todo@example.com
DTSTART:19920415T133000Z
DUE:19920516T045959Z
SUMMARY:Yearly Income Tax Preparation
RRULE:FREQ=YEARLY
END:VTODO
END:VCALENDAR
"""
        cal_file = ICalendarFile([yearly_vtodo], "text/calendar")

        # Test unbounded query (no time range) - should NOT expand recurring events
        filter_unbounded = CalendarFilter(ZoneInfo("UTC"))
        filter_unbounded.filter_subcomponent("VCALENDAR").filter_subcomponent("VTODO")

        # This should return True and complete quickly without infinite expansion
        result = filter_unbounded.check("test.ics", cal_file)
        self.assertTrue(result)

        # The original calendar should have only 1 VTODO component
        self.assertEqual(len(cal_file.calendar.subcomponents), 1)

        # Test bounded query (with time range) - should expand within bounds
        filter_bounded = CalendarFilter(ZoneInfo("UTC"))
        filter_bounded.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VTODO"
        ).filter_time_range(
            start=self._tzify(datetime(1992, 1, 1, 0, 0, 0)),
            end=self._tzify(datetime(1995, 12, 31, 23, 59, 59)),
        )

        # This should also return True and expand only within the time range
        result_bounded = filter_bounded.check("test.ics", cal_file)
        self.assertTrue(result_bounded)

    def test_unbounded_query_overflow_prevention(self):
        """Test that unbounded queries with date-only events don't cause overflow.

        Regression test for issue #538 where querying recurring date-only events
        with no end date caused OverflowError when trying to add 1 day to MAX_EXPANSION_TIME.
        """
        from xandikos.icalendar import MAX_EXPANSION_TIME

        # Create a calendar with a daily recurring date-only event
        daily_event = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:daily-event@example.com
DTSTART;VALUE=DATE:20200101
SUMMARY:Daily Event
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
"""
        cal_file = ICalendarFile([daily_event], "text/calendar")

        # Test unbounded query (end date at MAX_EXPANSION_TIME)
        # This should not cause OverflowError when adding 1 day for date-only events
        filter_unbounded = CalendarFilter(ZoneInfo("UTC"))
        filter_unbounded.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self._tzify(datetime(2020, 1, 1, 0, 0, 0)),
            end=MAX_EXPANSION_TIME,  # This triggers the overflow if not handled
        )

        # This should complete without OverflowError
        result = filter_unbounded.check("test.ics", cal_file)
        self.assertTrue(result)


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
        # With substring matching, "foobar" is found in "foobarblah"
        self.assertTrue(tm.match_indexes({None: [b"foobarblah"]}))

    def test_unknown_type(self):
        tm = TextMatcher("dontknow", "foobar")
        self.assertFalse(tm.match(object()))
        # With substring matching, "foobar" is found in "foobarblah"
        self.assertTrue(tm.match_indexes({None: [b"foobarblah"]}))

    def test_unknown_collation(self):
        self.assertRaises(
            _mod_collation.UnknownCollation,
            TextMatcher,
            "summary",
            "foobar",
            collation="i;blah",
        )

    def test_substring_match(self):
        # Test that text matching uses substring search as per RFC
        tm = TextMatcher("summary", "bar")
        self.assertTrue(tm.match(vText("foobar")))
        self.assertTrue(tm.match(vText("bar")))
        self.assertTrue(tm.match(vText("barbaz")))
        self.assertTrue(tm.match(vText("foobarbaz")))
        self.assertFalse(tm.match(vText("foo")))
        self.assertFalse(tm.match(vText("ba")))
        # Test case insensitive substring match
        self.assertTrue(tm.match(vText("FOOBAR")))


class ApplyTimeRangeVeventTests(unittest.TestCase):
    def _tzify(self, dt):
        return as_tz_aware_ts(dt, ZoneInfo("UTC"))

    def test_missing_dtstart(self):
        ev = Event()
        self.assertRaises(
            MissingProperty,
            apply_time_range_vevent,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
            ev,
            self._tzify,
        )


class ApplyTimeRangeVavailabilityTests(unittest.TestCase):
    def _tzify(self, dt):
        return as_tz_aware_ts(dt, ZoneInfo("UTC"))

    def test_vavailability_with_dtstart_dtend(self):
        """Test VAVAILABILITY with DTSTART and DTEND."""
        from icalendar.cal import Component

        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail.add("DTEND", datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc))

        # Time range that overlaps
        self.assertTrue(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

        # Time range before availability
        self.assertFalse(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

        # Time range after availability
        self.assertFalse(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 19, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

    def test_vavailability_with_dtstart_duration(self):
        """Test VAVAILABILITY with DTSTART and DURATION."""
        from icalendar.cal import Component

        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
        vavail.add("DURATION", vDuration(timedelta(hours=8)))

        # Time range that overlaps
        self.assertTrue(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

    def test_vavailability_only_dtstart(self):
        """Test VAVAILABILITY with only DTSTART."""
        from icalendar.cal import Component

        vavail = Component()
        vavail.name = "VAVAILABILITY"
        vavail.add("DTSTART", datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))

        # Any time range after dtstart should match
        self.assertTrue(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

        # Time range before dtstart should not match
        self.assertFalse(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

    def test_vavailability_no_time_properties(self):
        """Test VAVAILABILITY with no time properties."""
        from icalendar.cal import Component

        vavail = Component()
        vavail.name = "VAVAILABILITY"

        # Should always match when no time properties
        self.assertTrue(
            apply_time_range_vavailability(
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                vavail,
                self._tzify,
            )
        )

    def test_available_subcomponent(self):
        """Test AVAILABLE subcomponent time range filtering."""
        from icalendar.cal import Component

        available = Component()
        available.name = "AVAILABLE"
        available.add("DTSTART", datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        available.add("DTEND", datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))

        # Should use same logic as VAVAILABILITY
        self.assertTrue(
            apply_time_range_available(
                datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 12, 45, tzinfo=timezone.utc),
                available,
                self._tzify,
            )
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

    def test_expand_with_exdate(self):
        """Test expansion of recurring events with EXDATE.

        This test reproduces issue #528 where EXDATE values were causing
        a TypeError when dateutil tried to sort them, because vDDDLists
        objects don't support comparison operations.
        """
        from icalendar import Calendar

        # Create a calendar with a recurring event and exception dates
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-exdate@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
RRULE:FREQ=DAILY;COUNT=10
EXDATE:20240102T100000Z,20240103T100000Z
SUMMARY:Daily Event with Exceptions
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Expand the calendar
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, tzinfo=timezone.utc)

        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (10 total - 2 excluded = 8)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 8)

        # Verify the excluded dates are not present
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        excluded_dates = [
            datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc),
        ]
        for excluded in excluded_dates:
            self.assertNotIn(excluded, event_dates)

        # Verify the included dates are correct
        expected_dates = [
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 4, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 6, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 7, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 8, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
        ]
        self.assertEqual(event_dates, expected_dates)

    def test_expand_with_multiple_exdate_properties(self):
        """Test expansion with multiple EXDATE properties on separate lines.

        According to RFC 5545, EXDATE can appear multiple times in a component.
        This tests that we correctly handle a list of vDDDLists objects.
        """
        from icalendar import Calendar

        # Create a calendar with multiple EXDATE properties
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-multi-exdate@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
RRULE:FREQ=DAILY;COUNT=7
EXDATE:20240102T100000Z
EXDATE:20240103T100000Z
EXDATE:20240105T100000Z
SUMMARY:Event with Multiple EXDATE Properties
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Expand the calendar
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, tzinfo=timezone.utc)

        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (7 total - 3 excluded = 4)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 4)

        # Verify the excluded dates are not present
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        excluded_dates = [
            datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 10, 0, 0, tzinfo=timezone.utc),
        ]
        for excluded in excluded_dates:
            self.assertNotIn(excluded, event_dates)

        # Verify the included dates are correct
        expected_dates = [
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 4, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 6, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 7, 10, 0, 0, tzinfo=timezone.utc),
        ]
        self.assertEqual(event_dates, expected_dates)

    def test_expand_with_rdate(self):
        """Test expansion with RDATE (recurrence dates).

        RDATE adds additional occurrences to a recurring event.
        This tests that we correctly handle vDDDLists for RDATE.
        """
        from icalendar import Calendar

        # Create a calendar with RDATE
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-rdate@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
RRULE:FREQ=WEEKLY;COUNT=2
RDATE:20240110T100000Z,20240120T100000Z
SUMMARY:Event with RDATE
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)

        # Expand the calendar
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (2 from RRULE + 2 from RDATE = 4)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 4)

        # Verify all dates are present
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        expected_dates = [
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),  # RRULE
            datetime(2024, 1, 8, 10, 0, 0, tzinfo=timezone.utc),  # RRULE
            datetime(2024, 1, 10, 10, 0, 0, tzinfo=timezone.utc),  # RDATE
            datetime(2024, 1, 20, 10, 0, 0, tzinfo=timezone.utc),  # RDATE
        ]
        self.assertEqual(event_dates, expected_dates)


class MixedDateDatetimeTests(unittest.TestCase):
    """Test handling of mixed date/datetime types in EXDATE/RDATE.

    These tests cover issue #528 where mixed types would cause TypeError
    when dateutil tried to compare date and datetime objects.
    """

    def test_datetime_dtstart_with_date_exdate(self):
        """Test DTSTART is datetime, EXDATE is date (VALUE=DATE)."""
        from icalendar import Calendar

        # This reproduces the case where EXDATE;VALUE=DATE is used with
        # a datetime DTSTART, which is technically non-compliant but happens
        # in practice
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-mixed-1@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
RRULE:FREQ=DAILY;COUNT=5
EXDATE;VALUE=DATE:20240102
SUMMARY:Event with datetime DTSTART and date EXDATE
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)

        # This should not raise TypeError
        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (5 total - 1 excluded = 4)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 4)

        # Verify Jan 2 is excluded
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        excluded_date = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        self.assertNotIn(excluded_date, event_dates)

    def test_date_dtstart_with_datetime_exdate(self):
        """Test DTSTART is date, EXDATE is datetime."""
        from icalendar import Calendar

        # This reproduces the case where EXDATE is a full datetime but
        # DTSTART is just a date (all-day event)
        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-mixed-2@example.com
DTSTART;VALUE=DATE:20240101
RRULE:FREQ=DAILY;COUNT=5
EXDATE:20240102T100000Z
SUMMARY:Event with date DTSTART and datetime EXDATE
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)

        # This should not raise TypeError
        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (5 total - 1 excluded = 4)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 4)

        # Verify Jan 2 is excluded (the date portion should match)
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        # When DTSTART is a date, occurrences are datetimes at midnight
        # Convert to just dates for comparison since these are all-day events
        event_date_only = [
            d.date() if isinstance(d, datetime) else d for d in event_dates
        ]
        self.assertNotIn(date(2024, 1, 2), event_date_only)

    def test_datetime_dtstart_with_date_rdate(self):
        """Test DTSTART is datetime, RDATE is date (VALUE=DATE)."""
        from icalendar import Calendar

        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-rdate-mixed@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
RRULE:FREQ=WEEKLY;COUNT=2
RDATE;VALUE=DATE:20240110
SUMMARY:Event with datetime DTSTART and date RDATE
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        # This should not raise TypeError
        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (2 from RRULE + 1 from RDATE = 3)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 3)

        # Verify Jan 10 is included from RDATE
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        rdate_occurrence = datetime(2024, 1, 10, 10, 0, 0, tzinfo=timezone.utc)
        self.assertIn(rdate_occurrence, event_dates)

    def test_multiple_mixed_exdates(self):
        """Test multiple EXDATE properties with mixed types."""
        from icalendar import Calendar

        test_ical = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-multi-mixed@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
RRULE:FREQ=DAILY;COUNT=10
EXDATE;VALUE=DATE:20240102
EXDATE:20240103T100000Z
EXDATE;VALUE=DATE:20240105
SUMMARY:Event with multiple mixed EXDATEs
END:VEVENT
END:VCALENDAR"""

        cal = Calendar.from_ical(test_ical)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # This should not raise TypeError
        expanded = expand_calendar_rrule(cal, start, end)

        # Verify we got the expected events (10 total - 3 excluded = 7)
        events = [comp for comp in expanded.walk() if comp.name == "VEVENT"]
        self.assertEqual(len(events), 7)

        # Verify the excluded dates
        event_dates = sorted([ev["DTSTART"].dt for ev in events])
        excluded_dates = [
            datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 10, 0, 0, tzinfo=timezone.utc),
        ]
        for excluded in excluded_dates:
            self.assertNotIn(excluded, event_dates)


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


class RRuleFilteringEdgeCasesTests(unittest.TestCase):
    """Additional tests for rrule filtering edge cases and overlap scenarios."""

    def test_event_starts_before_range_extends_into_it(self):
        """Test filtering catches events that start before the range but extend into it."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Event: 9:00-11:00 every day
        event = Event()
        event.add("uid", "test-overlap@example.com")
        event.add("summary", "Morning Meeting")
        event.add("dtstart", datetime(2024, 1, 1, 9, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("dtend", datetime(2024, 1, 1, 11, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event)

        # Filter: 10:00-12:00 on Jan 3
        start = datetime(2024, 1, 3, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include Jan 3 event (9:00-11:00) because it overlaps 10:00-11:00
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["DTSTART"].dt,
            datetime(2024, 1, 3, 9, 0, 0, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(
            events[0]["DTEND"].dt,
            datetime(2024, 1, 3, 11, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

    def test_event_spans_entire_range(self):
        """Test filtering includes events that completely span the filter range."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Event: All-day event
        event = Event()
        event.add("uid", "test-allday@example.com")
        event.add("summary", "Conference")
        event.add("dtstart", datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("dtend", datetime(2024, 1, 1, 23, 59, 59, tzinfo=ZoneInfo("UTC")))
        event.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event)

        # Filter: Small window within the day
        start = datetime(2024, 1, 3, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 3, 11, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include Jan 3 all-day event
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["DTSTART"].dt.date(), date(2024, 1, 3))

    def test_event_with_duration_overlap(self):
        """Test filtering with DURATION property instead of DTEND."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Event with 3-hour duration starting at 8:00
        event = Event()
        event.add("uid", "test-duration@example.com")
        event.add("summary", "Workshop")
        event.add("dtstart", datetime(2024, 1, 1, 8, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("duration", timedelta(hours=3))  # Ends at 11:00
        event.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event)

        # Filter: 10:00-12:00
        start = datetime(2024, 1, 3, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include the event (8:00-11:00 overlaps with 10:00-12:00)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["DTSTART"].dt,
            datetime(2024, 1, 3, 8, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

    def test_floating_time_overlap(self):
        """Test filtering with floating time (naive datetime) events."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Floating time event (no timezone)
        event = Event()
        event.add("uid", "test-floating@example.com")
        event.add("summary", "Local Meeting")
        event.add("dtstart", datetime(2024, 1, 1, 9, 0, 0))  # No timezone
        event.add("dtend", datetime(2024, 1, 1, 11, 0, 0))  # No timezone
        event.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event)

        # Filter with timezone
        start = datetime(2024, 1, 3, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include the event
        self.assertEqual(len(events), 1)
        # Event should remain floating (no timezone)
        self.assertIsNone(events[0]["DTSTART"].dt.tzinfo)

    def test_date_only_event_overlap(self):
        """Test filtering with date-only (all-day) events."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Date-only event (2-day event)
        event = Event()
        event.add("uid", "test-dateonly@example.com")
        event.add("summary", "Two Day Workshop")
        event.add("dtstart", date(2024, 1, 1))
        event.add("dtend", date(2024, 1, 3))  # Non-inclusive, so Jan 1-2
        event.add("rrule", {"freq": "weekly", "count": 3})
        cal.add_component(event)

        # Filter that overlaps with second day of first occurrence
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 2, 14, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include the first occurrence (Jan 1-2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["DTSTART"].dt, date(2024, 1, 1))
        self.assertEqual(events[0]["DTEND"].dt, date(2024, 1, 3))

    def test_exception_event_in_range_master_out(self):
        """Test exception event that falls in range when master occurrence would not."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Master event: 9:00-10:00 daily
        event = Event()
        event.add("uid", "test-exception@example.com")
        event.add("summary", "Daily Standup")
        event.add("dtstart", datetime(2024, 1, 1, 9, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("dtend", datetime(2024, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event)

        # Exception: Jan 3 moved to 14:00-15:00
        exception = Event()
        exception.add("uid", "test-exception@example.com")
        exception.add("summary", "Daily Standup (moved)")
        exception.add("dtstart", datetime(2024, 1, 3, 14, 0, 0, tzinfo=ZoneInfo("UTC")))
        exception.add("dtend", datetime(2024, 1, 3, 15, 0, 0, tzinfo=ZoneInfo("UTC")))
        exception.add(
            "recurrence-id", datetime(2024, 1, 3, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
        )
        cal.add_component(exception)

        # Filter: 13:00-16:00 on Jan 3 (excludes original time, includes exception)
        start = datetime(2024, 1, 3, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 3, 16, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include only the exception event
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["DTSTART"].dt,
            datetime(2024, 1, 3, 14, 0, 0, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(events[0]["SUMMARY"], "Daily Standup (moved)")

    def test_multiple_overlapping_events(self):
        """Test multiple events with different overlap patterns."""
        cal = Calendar()
        cal.add("prodid", "-//Test//Test//EN")
        cal.add("version", "2.0")

        # Event 1: Starts before, ends in range (8:00-10:30)
        event1 = Event()
        event1.add("uid", "test-overlap1@example.com")
        event1.add("summary", "Morning Session")
        event1.add("dtstart", datetime(2024, 1, 1, 8, 0, 0, tzinfo=ZoneInfo("UTC")))
        event1.add("dtend", datetime(2024, 1, 1, 10, 30, 0, tzinfo=ZoneInfo("UTC")))
        event1.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event1)

        # Event 2: Completely within range (10:00-11:00)
        event2 = Event()
        event2.add("uid", "test-overlap2@example.com")
        event2.add("summary", "Mid Session")
        event2.add("dtstart", datetime(2024, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("UTC")))
        event2.add("dtend", datetime(2024, 1, 1, 11, 0, 0, tzinfo=ZoneInfo("UTC")))
        event2.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event2)

        # Event 3: Starts in range, ends after (11:30-13:00)
        event3 = Event()
        event3.add("uid", "test-overlap3@example.com")
        event3.add("summary", "Late Session")
        event3.add("dtstart", datetime(2024, 1, 1, 11, 30, 0, tzinfo=ZoneInfo("UTC")))
        event3.add("dtend", datetime(2024, 1, 1, 13, 0, 0, tzinfo=ZoneInfo("UTC")))
        event3.add("rrule", {"freq": "daily", "count": 5})
        cal.add_component(event3)

        # Filter: 10:00-12:00 on Jan 3
        start = datetime(2024, 1, 3, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 1, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        expanded = expand_calendar_rrule(cal, start, end)
        events = [c for c in expanded.subcomponents if c.name == "VEVENT"]

        # Should include all three events for Jan 3
        self.assertEqual(len(events), 3)
        summaries = sorted([e["SUMMARY"] for e in events])
        self.assertEqual(summaries, ["Late Session", "Mid Session", "Morning Session"])


class EventOverlapsRangeTests(unittest.TestCase):
    """Tests for _event_overlaps_range function."""

    def setUp(self):
        self.start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        self.end = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

    def test_vevent_overlaps(self):
        """Test VEVENT component overlap detection."""
        event = Event()
        event.add("uid", "test-vevent@example.com")
        event.add("dtstart", datetime(2024, 1, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("dtend", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # Event 9:00-11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(event, self.start, self.end))

    def test_vevent_no_overlap(self):
        """Test VEVENT component that doesn't overlap."""
        event = Event()
        event.add("uid", "test-vevent@example.com")
        event.add("dtstart", datetime(2024, 1, 15, 13, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("dtend", datetime(2024, 1, 15, 14, 0, 0, tzinfo=ZoneInfo("UTC")))

        # Event 13:00-14:00 doesn't overlap with range 10:00-12:00
        self.assertFalse(_event_overlaps_range(event, self.start, self.end))

    def test_vtodo_with_due_overlaps(self):
        """Test VTODO component with DUE that overlaps."""
        todo = Todo()
        todo.add("uid", "test-todo@example.com")
        todo.add("due", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # TODO due at 11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(todo, self.start, self.end))

    def test_vtodo_with_due_no_overlap(self):
        """Test VTODO component with DUE that doesn't overlap."""
        todo = Todo()
        todo.add("uid", "test-todo@example.com")
        todo.add("due", datetime(2024, 1, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC")))

        # TODO due at 9:00 doesn't overlap with range 10:00-12:00
        self.assertFalse(_event_overlaps_range(todo, self.start, self.end))

    def test_vtodo_with_dtstart_and_due(self):
        """Test VTODO component with both DTSTART and DUE."""
        todo = Todo()
        todo.add("uid", "test-todo@example.com")
        todo.add("dtstart", datetime(2024, 1, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC")))
        todo.add("due", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # TODO 9:00-11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(todo, self.start, self.end))

    def test_vtodo_no_dates(self):
        """Test VTODO component with no dates (should match according to RFC)."""
        todo = Todo()
        todo.add("uid", "test-todo@example.com")
        todo.add("summary", "No dates")

        # TODO with no dates should match any range per RFC
        self.assertTrue(_event_overlaps_range(todo, self.start, self.end))

    def test_vtodo_with_completed(self):
        """Test VTODO component with COMPLETED date."""
        todo = Todo()
        todo.add("uid", "test-todo@example.com")
        todo.add("completed", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # TODO completed at 11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(todo, self.start, self.end))

    def test_vjournal_overlaps(self):
        """Test VJOURNAL component overlap detection."""
        from icalendar.cal import Journal

        journal = Journal()
        journal.add("uid", "test-journal@example.com")
        journal.add("dtstart", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # Journal at 11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(journal, self.start, self.end))

    def test_vjournal_no_overlap(self):
        """Test VJOURNAL component that doesn't overlap."""
        from icalendar.cal import Journal

        journal = Journal()
        journal.add("uid", "test-journal@example.com")
        journal.add("dtstart", datetime(2024, 1, 15, 13, 0, 0, tzinfo=ZoneInfo("UTC")))

        # Journal at 13:00 doesn't overlap with range 10:00-12:00
        self.assertFalse(_event_overlaps_range(journal, self.start, self.end))

    def test_vfreebusy_overlaps(self):
        """Test VFREEBUSY component overlap detection."""
        from icalendar.cal import FreeBusy

        freebusy = FreeBusy()
        freebusy.add("uid", "test-freebusy@example.com")
        freebusy.add("dtstart", datetime(2024, 1, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC")))
        freebusy.add("dtend", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # FreeBusy 9:00-11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(freebusy, self.start, self.end))

    def test_valarm_overlaps(self):
        """Test VALARM component overlap detection."""
        # For VALARM testing, we need to create an enriched alarm with absolute trigger
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", "Reminder")
        # Use absolute trigger time that falls within our range
        alarm.add("trigger", datetime(2024, 1, 15, 10, 45, 0, tzinfo=ZoneInfo("UTC")))

        # Test the alarm component directly
        self.assertTrue(_event_overlaps_range(alarm, self.start, self.end))

    def test_valarm_no_overlap(self):
        """Test VALARM component that doesn't overlap."""
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", "Reminder")
        # Use absolute trigger time outside our range
        alarm.add("trigger", datetime(2024, 1, 15, 13, 0, 0, tzinfo=ZoneInfo("UTC")))

        # Test the alarm component directly
        self.assertFalse(_event_overlaps_range(alarm, self.start, self.end))

    def test_valarm_relative_trigger_raises_error(self):
        """Test VALARM component with relative trigger raises TypeError."""
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", "Reminder")
        # Use relative trigger time (this should raise an error)
        alarm.add("trigger", vDuration(-timedelta(minutes=15)))

        # Test the alarm component directly - should raise TypeError
        with self.assertRaises(TypeError) as cm:
            _event_overlaps_range(alarm, self.start, self.end)

        self.assertIn("relative trigger", str(cm.exception))

    def test_unknown_component_with_dtstart(self):
        """Test unknown component type with DTSTART."""
        from icalendar.cal import Component

        # Create a custom component
        comp = Component()
        comp.name = "VCUSTOM"
        comp.add("uid", "test-custom@example.com")
        comp.add("dtstart", datetime(2024, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC")))

        # Should use fallback logic
        self.assertTrue(_event_overlaps_range(comp, self.start, self.end))

    def test_unknown_component_without_dtstart(self):
        """Test unknown component type without DTSTART."""
        from icalendar.cal import Component

        # Create a custom component without DTSTART
        comp = Component()
        comp.name = "VCUSTOM"
        comp.add("uid", "test-custom@example.com")
        comp.add("summary", "No start time")

        # Should return False for unknown components without DTSTART
        self.assertFalse(_event_overlaps_range(comp, self.start, self.end))

    def test_vevent_with_duration(self):
        """Test VEVENT with DURATION instead of DTEND."""
        event = Event()
        event.add("uid", "test-duration@example.com")
        event.add("dtstart", datetime(2024, 1, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC")))
        event.add("duration", vDuration(timedelta(hours=2)))  # 9:00-11:00

        # Event 9:00-11:00 overlaps with range 10:00-12:00
        self.assertTrue(_event_overlaps_range(event, self.start, self.end))

    def test_all_day_event(self):
        """Test all-day event (date only)."""
        event = Event()
        event.add("uid", "test-allday@example.com")
        event.add("dtstart", date(2024, 1, 15))
        event.add("dtend", date(2024, 1, 16))

        # All-day event on Jan 15 should overlap with range 10:00-12:00 on Jan 15
        self.assertTrue(_event_overlaps_range(event, self.start, self.end))

    def test_all_day_event_no_overlap(self):
        """Test all-day event that doesn't overlap."""
        event = Event()
        event.add("uid", "test-allday@example.com")
        event.add("dtstart", date(2024, 1, 16))
        event.add("dtend", date(2024, 1, 17))

        # All-day event on Jan 16 shouldn't overlap with range 10:00-12:00 on Jan 15
        self.assertFalse(_event_overlaps_range(event, self.start, self.end))
