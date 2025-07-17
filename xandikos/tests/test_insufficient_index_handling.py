"""Tests for InsufficientIndexDataError handling in store filtering."""

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from xandikos.icalendar import CalendarFilter, ICalendarFile
from xandikos.store import InsufficientIndexDataError


class InsufficientIndexHandlingTest(unittest.TestCase):
    """Test that InsufficientIndexDataError is properly handled by the filtering system."""

    def setUp(self):
        # Create a test calendar with RRULE
        self.test_calendar = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20150527T100000Z
DTEND:20150527T110000Z
RRULE:FREQ=YEARLY;COUNT=3
SUMMARY:Test recurring event
UID:test-rrule@example.com
END:VEVENT
END:VCALENDAR
"""
        self.cal = ICalendarFile([self.test_calendar], "text/calendar")

        def tzify(dt):
            if hasattr(dt, "tzinfo") and dt.tzinfo is None:
                return dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt

        self.tzify = tzify

    def test_insufficient_index_data_raises_exception(self):
        """Test that insufficient index data raises InsufficientIndexDataError."""
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self.tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self.tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        # Empty indexes should raise exception
        empty_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }

        with self.assertRaises(InsufficientIndexDataError) as cm:
            filter.check_from_indexes("file", empty_indexes)

        self.assertIn("No valid index entries found", str(cm.exception))

    def test_missing_component_index_raises_exception(self):
        """Test that missing component index raises InsufficientIndexDataError."""
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent("VEVENT")

        # Missing component marker
        incomplete_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20160527T100000Z"],
            # Missing "C=VCALENDAR/C=VEVENT": True
        }

        with self.assertRaises(InsufficientIndexDataError) as cm:
            filter.check_from_indexes("file", incomplete_indexes)

        self.assertIn("Missing component index", str(cm.exception))

    def test_sufficient_index_data_works_normally(self):
        """Test that sufficient index data works without exceptions."""
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self.tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self.tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        # Complete indexes with RRULE should work normally
        complete_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20150527T100000Z"],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [b"20150527T110000Z"],
            "C=VCALENDAR/C=VEVENT/P=RRULE": [b"FREQ=YEARLY;COUNT=3"],
            "C=VCALENDAR/C=VEVENT/P=DURATION": [],
            "C=VCALENDAR/C=VEVENT": True,
        }

        # Should return True (matches 2016 occurrence) without raising exception
        result = filter.check_from_indexes("file", complete_indexes)
        self.assertTrue(result)

    def test_full_file_check_fallback_works(self):
        """Test that full file check works correctly as fallback."""
        filter = CalendarFilter(ZoneInfo("UTC"))
        filter.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        ).filter_time_range(
            start=self.tzify(datetime(2016, 5, 26, 0, 0, 0)),
            end=self.tzify(datetime(2016, 5, 28, 0, 0, 0)),
        )

        # Full file check should work even when index-based check fails
        result = filter.check("file", self.cal)
        self.assertTrue(result)  # Should match the 2016 occurrence


if __name__ == "__main__":
    unittest.main()
