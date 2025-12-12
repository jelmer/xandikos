"""Test for the time-range filtering regression in Store._iter_with_filter_indexes."""

import unittest
from datetime import datetime, timezone

from xandikos.icalendar import (
    ICalendarFile,
    CalendarFilter,
    ComponentFilter,
    ComponentTimeRangeMatcher,
)
from xandikos.store.git import BareGitStore


# Calendar data matching the CalDAV server checker test
MONTHLY_RECURRING_EVENT = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//python-caldav//caldav//en_DK
BEGIN:VEVENT
SUMMARY:monthly recurring event
DTSTART:20000112T120000Z
DTEND:20000112T130000Z
DTSTAMP:20250714T170716Z
UID:csc_monthly_recurring_event
RRULE:FREQ=MONTHLY
END:VEVENT
END:VCALENDAR
"""

SIMPLE_EVENT_JAN1 = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//python-caldav//caldav//en_DK
BEGIN:VEVENT
SUMMARY:simple event with a start time and an end time
DTSTART:20000101T120000Z
DTEND:20000101T130000Z
DTSTAMP:20250714T170715Z
UID:csc_simple_event1
END:VEVENT
END:VCALENDAR
"""

SIMPLE_EVENT_JAN2 = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//python-caldav//caldav//en_DK
BEGIN:VEVENT
SUMMARY:event with a start time but no end time
DTSTART:20000102T120000Z
DTSTAMP:20250714T170716Z
UID:csc_simple_event2
END:VEVENT
END:VCALENDAR
"""

SIMPLE_EVENT_JAN3 = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//python-caldav//caldav//en_DK
BEGIN:VEVENT
SUMMARY:event with a start date but no end date
DTSTART;VALUE=DATE:20000103
DTSTAMP:20250714T170716Z
UID:csc_simple_event3
END:VEVENT
END:VCALENDAR
"""


class TimeRangeFilterRegressionTest(unittest.TestCase):
    """Test for the regression where time-range filters returned all files."""

    def setUp(self):
        """Set up a test store with calendar files."""
        self.store = BareGitStore.create_memory()
        self.store.load_extra_file_handler(ICalendarFile)

        # Import test calendar files
        self.store.import_one(
            "csc_monthly_recurring_event.ics",
            "text/calendar",
            [MONTHLY_RECURRING_EVENT],
        )
        self.store.import_one(
            "csc_simple_event1.ics", "text/calendar", [SIMPLE_EVENT_JAN1]
        )
        self.store.import_one(
            "csc_simple_event2.ics", "text/calendar", [SIMPLE_EVENT_JAN2]
        )
        self.store.import_one(
            "csc_simple_event3.ics", "text/calendar", [SIMPLE_EVENT_JAN3]
        )

    def test_time_range_filter_without_indexes(self):
        """Test time-range filtering without indexes (naive path)."""
        # Create filter for Feb 12-13, 2000
        start = datetime(2000, 2, 12, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2000, 2, 13, 0, 0, 0, tzinfo=timezone.utc)

        cal_filter = CalendarFilter(timezone.utc)
        comp_filter = ComponentFilter("VCALENDAR")
        event_filter = ComponentFilter("VEVENT")
        event_filter.time_range = ComponentTimeRangeMatcher(start, end, comp="VEVENT")
        comp_filter.children.append(event_filter)
        cal_filter.children.append(comp_filter)

        # Get matching files
        matches = list(self.store.iter_with_filter(cal_filter))

        # Only the monthly recurring event should match (it recurs on the 12th)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "csc_monthly_recurring_event.ics")

    def test_time_range_filter_with_indexes(self):
        """Test time-range filtering with indexes (the regression case)."""
        # Force indexing by setting threshold to 0
        self.store.index_manager.indexing_threshold = 0

        # Create filter for Feb 12-13, 2000
        start = datetime(2000, 2, 12, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2000, 2, 13, 0, 0, 0, tzinfo=timezone.utc)

        cal_filter = CalendarFilter(timezone.utc)
        comp_filter = ComponentFilter("VCALENDAR")
        event_filter = ComponentFilter("VEVENT")
        event_filter.time_range = ComponentTimeRangeMatcher(start, end, comp="VEVENT")
        comp_filter.children.append(event_filter)
        cal_filter.children.append(comp_filter)

        # First, we need to tell the index what keys we need
        # We need to reset with ALL the keys the filter might need
        all_keys = []
        for key_set in cal_filter.index_keys():
            all_keys.extend(key_set)
        # Remove duplicates
        all_keys = list(set(all_keys))
        self.store.index.reset(all_keys)

        # Force index creation
        for name, content_type, etag in self.store.iter_with_etag():
            file = self.store.get_file(name, content_type, etag)
            indexes = file.get_indexes(self.store.index.available_keys())
            self.store.index.add_values(name, etag, indexes)

        # Get matching files
        matches = list(self.store.iter_with_filter(cal_filter))

        # This is the regression test:
        # Without the fix, ALL calendar files would be returned because
        # check_from_indexes returns True for time-range queries
        self.assertEqual(
            len(matches),
            1,
            "Time-range filter should only return events in the range, "
            "not all calendar files",
        )
        self.assertEqual(matches[0][0], "csc_monthly_recurring_event.ics")

    def test_check_from_indexes_behavior(self):
        """Test that check_from_indexes works properly with expanded indexes."""
        # Create a filter with a time range
        cal_filter = CalendarFilter(timezone.utc)
        comp_filter = ComponentFilter("VCALENDAR")
        event_filter = ComponentFilter("VEVENT")
        event_filter.time_range = ComponentTimeRangeMatcher(
            datetime(2000, 2, 12, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2000, 2, 13, 0, 0, 0, tzinfo=timezone.utc),
            comp="VEVENT",
        )
        comp_filter.children.append(event_filter)
        cal_filter.children.append(comp_filter)

        # With proper expanded indexes, check_from_indexes should be able to determine
        # the result accurately for time-range queries
        matching_indexes = {
            "C=VCALENDAR/C=VEVENT": [True],
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20000212T120000Z"],  # Matches range
        }
        self.assertTrue(cal_filter.check_from_indexes("test.ics", matching_indexes))

        non_matching_indexes = {
            "C=VCALENDAR/C=VEVENT": [True],
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20000101T120000Z"],  # Outside range
        }
        self.assertFalse(
            cal_filter.check_from_indexes("test.ics", non_matching_indexes)
        )


if __name__ == "__main__":
    unittest.main()
