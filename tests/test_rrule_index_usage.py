"""Test that RRULE indexes are properly created and exclusively used for VEVENT filtering."""

import unittest
from datetime import datetime, timezone

from xandikos.icalendar import (
    ICalendarFile,
    CalendarFilter,
    ComponentFilter,
    ComponentTimeRangeMatcher,
)
from xandikos.store import InsufficientIndexDataError


# Test calendar with RRULE
RRULE_VEVENT = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
SUMMARY:Weekly recurring event
DTSTART:20200101T100000Z
DTEND:20200101T110000Z
RRULE:FREQ=WEEKLY;COUNT=5
UID:weekly-event
END:VEVENT
END:VCALENDAR
"""

# Test calendar without RRULE
SIMPLE_VEVENT = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
SUMMARY:Simple one-time event
DTSTART:20200101T100000Z
DTEND:20200101T110000Z
UID:simple-event
END:VEVENT
END:VCALENDAR
"""

# Test calendar with RRULE but no DTEND (using DURATION)
RRULE_WITH_DURATION = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
SUMMARY:Daily recurring event with duration
DTSTART:20200201T140000Z
DURATION:PT2H
RRULE:FREQ=DAILY;COUNT=3
UID:daily-duration-event
END:VEVENT
END:VCALENDAR
"""


class RRuleIndexUsageTest(unittest.TestCase):
    """Test that RRULE indexes are created and used correctly for VEVENT filtering."""

    def test_rrule_indexes_are_created(self):
        """Test that RRULE indexes are properly created for VEVENTs with RRULE."""
        cal = ICalendarFile([RRULE_VEVENT], "text/calendar")

        # Get indexes - should include RRULE
        indexes = cal.get_indexes(
            [
                "C=VCALENDAR/C=VEVENT/P=DTSTART",
                "C=VCALENDAR/C=VEVENT/P=DTEND",
                "C=VCALENDAR/C=VEVENT/P=RRULE",
                "C=VCALENDAR/C=VEVENT/P=DURATION",
            ]
        )

        # Verify RRULE index is created
        self.assertIn("C=VCALENDAR/C=VEVENT/P=RRULE", indexes)
        self.assertEqual(len(indexes["C=VCALENDAR/C=VEVENT/P=RRULE"]), 1)
        self.assertEqual(
            indexes["C=VCALENDAR/C=VEVENT/P=RRULE"][0], b"FREQ=WEEKLY;COUNT=5"
        )

        # Verify other standard indexes
        self.assertIn("C=VCALENDAR/C=VEVENT/P=DTSTART", indexes)
        self.assertEqual(
            indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"][0], b"20200101T100000Z"
        )

        self.assertIn("C=VCALENDAR/C=VEVENT/P=DTEND", indexes)
        self.assertEqual(
            indexes["C=VCALENDAR/C=VEVENT/P=DTEND"][0], b"20200101T110000Z"
        )

    def test_rrule_indexes_not_created_for_simple_events(self):
        """Test that RRULE indexes are empty for events without RRULE."""
        cal = ICalendarFile([SIMPLE_VEVENT], "text/calendar")

        indexes = cal.get_indexes(
            ["C=VCALENDAR/C=VEVENT/P=DTSTART", "C=VCALENDAR/C=VEVENT/P=RRULE"]
        )

        # RRULE index should be empty
        self.assertIn("C=VCALENDAR/C=VEVENT/P=RRULE", indexes)
        self.assertEqual(indexes["C=VCALENDAR/C=VEVENT/P=RRULE"], [])

        # But DTSTART should still be there
        self.assertEqual(
            indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"][0], b"20200101T100000Z"
        )

    def test_time_range_filter_uses_rrule_indexes_exclusively(self):
        """Test that time-range filtering uses RRULE indexes and doesn't expand events in indexes."""
        cal = ICalendarFile([RRULE_VEVENT], "text/calendar")

        # Create time-range filter that should match one occurrence
        filter = CalendarFilter(timezone.utc)
        comp_filter = ComponentFilter("VCALENDAR")
        event_filter = ComponentFilter("VEVENT")
        # Filter for second week - should match the second occurrence
        event_filter.time_range = ComponentTimeRangeMatcher(
            datetime(2020, 1, 8, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2020, 1, 9, 0, 0, 0, tzinfo=timezone.utc),
            comp="VEVENT",
        )
        comp_filter.children.append(event_filter)
        filter.children.append(comp_filter)

        # Get all indexes that the filter needs
        keys = []
        for key_set in filter.index_keys():
            keys.extend(key_set)

        # Verify RRULE is in the required keys
        self.assertIn("C=VCALENDAR/C=VEVENT/P=RRULE", keys)

        indexes = cal.get_indexes(keys)

        # Verify indexes contain only original event data, not expanded occurrences
        dtstart_values = indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"]
        self.assertEqual(
            len(dtstart_values), 1, "Should only contain original event DTSTART"
        )
        self.assertEqual(dtstart_values[0], b"20200101T100000Z")

        dtend_values = indexes["C=VCALENDAR/C=VEVENT/P=DTEND"]
        self.assertEqual(
            len(dtend_values), 1, "Should only contain original event DTEND"
        )
        self.assertEqual(dtend_values[0], b"20200101T110000Z")

        rrule_values = indexes["C=VCALENDAR/C=VEVENT/P=RRULE"]
        self.assertEqual(len(rrule_values), 1, "Should contain RRULE for expansion")
        self.assertEqual(rrule_values[0], b"FREQ=WEEKLY;COUNT=5")

        # Test that check_from_indexes correctly handles RRULE expansion
        self.assertTrue(filter.check_from_indexes("test.ics", indexes))

        # Test with a time range that shouldn't match any occurrences
        event_filter.time_range = ComponentTimeRangeMatcher(
            datetime(2020, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2020, 3, 2, 0, 0, 0, tzinfo=timezone.utc),
            comp="VEVENT",
        )
        self.assertFalse(filter.check_from_indexes("test.ics", indexes))

    def test_rrule_with_duration_uses_indexes(self):
        """Test that RRULE events with DURATION (no DTEND) work with indexes."""
        cal = ICalendarFile([RRULE_WITH_DURATION], "text/calendar")

        filter = CalendarFilter(timezone.utc)
        comp_filter = ComponentFilter("VCALENDAR")
        event_filter = ComponentFilter("VEVENT")
        # Filter for second day - should match second occurrence
        event_filter.time_range = ComponentTimeRangeMatcher(
            datetime(2020, 2, 2, 13, 0, 0, tzinfo=timezone.utc),
            datetime(2020, 2, 2, 17, 0, 0, tzinfo=timezone.utc),
            comp="VEVENT",
        )
        comp_filter.children.append(event_filter)
        filter.children.append(comp_filter)

        keys = []
        for key_set in filter.index_keys():
            keys.extend(key_set)

        indexes = cal.get_indexes(keys)

        # Verify indexes show only original event with DURATION
        self.assertEqual(len(indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"]), 1)
        self.assertEqual(
            indexes["C=VCALENDAR/C=VEVENT/P=DTSTART"][0], b"20200201T140000Z"
        )

        self.assertEqual(len(indexes["C=VCALENDAR/C=VEVENT/P=DURATION"]), 1)
        self.assertEqual(indexes["C=VCALENDAR/C=VEVENT/P=DURATION"][0], b"PT2H")

        self.assertEqual(len(indexes["C=VCALENDAR/C=VEVENT/P=RRULE"]), 1)
        self.assertEqual(
            indexes["C=VCALENDAR/C=VEVENT/P=RRULE"][0], b"FREQ=DAILY;COUNT=3"
        )

        # Should match (second occurrence: 2020-02-02 14:00-16:00)
        self.assertTrue(filter.check_from_indexes("test.ics", indexes))

    def test_insufficient_index_data_handling(self):
        """Test that InsufficientIndexDataError is raised when index data is missing."""
        filter = CalendarFilter(timezone.utc)
        comp_filter = ComponentFilter("VCALENDAR")
        event_filter = ComponentFilter("VEVENT")
        event_filter.time_range = ComponentTimeRangeMatcher(
            datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2020, 1, 2, 0, 0, 0, tzinfo=timezone.utc),
            comp="VEVENT",
        )
        comp_filter.children.append(event_filter)
        filter.children.append(comp_filter)

        # Test with missing DTSTART - this should return False (no match) not raise exception
        # because missing required properties means the event can't match
        incomplete_indexes = {
            "C=VCALENDAR/C=VEVENT": [True],
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [],  # Missing!
            "C=VCALENDAR/C=VEVENT/P=DTEND": [b"20200101T110000Z"],
            "C=VCALENDAR/C=VEVENT/P=RRULE": [],
        }

        # Should return False when essential data is missing
        result = filter.check_from_indexes("test.ics", incomplete_indexes)
        self.assertFalse(result, "Should return False when DTSTART is missing")

        # Test with missing component marker - this should raise InsufficientIndexDataError
        missing_component_indexes = {
            "C=VCALENDAR/C=VEVENT/P=DTSTART": [b"20200101T100000Z"],
            "C=VCALENDAR/C=VEVENT/P=DTEND": [b"20200101T110000Z"],
            "C=VCALENDAR/C=VEVENT/P=RRULE": [],
            # Missing "C=VCALENDAR/C=VEVENT": [True]
        }

        with self.assertRaises(InsufficientIndexDataError):
            filter.check_from_indexes("test.ics", missing_component_indexes)

    def test_time_range_matcher_includes_rrule_in_index_keys(self):
        """Test that ComponentTimeRangeMatcher includes RRULE in index keys for VEVENT."""
        # Test VEVENT time range matcher
        matcher = ComponentTimeRangeMatcher(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2020, 1, 2, tzinfo=timezone.utc),
            comp="VEVENT",
        )

        index_keys = matcher.index_keys()

        # Should include RRULE for VEVENT
        found_rrule = False
        for key_set in index_keys:
            if "P=RRULE" in key_set:
                found_rrule = True
                break

        self.assertTrue(
            found_rrule, "VEVENT time-range filter should include RRULE in index keys"
        )

        # Verify all expected properties are included
        all_props = []
        for key_set in index_keys:
            all_props.extend(key_set)

        expected_props = ["P=DTSTART", "P=DTEND", "P=DURATION", "P=RRULE"]
        for prop in expected_props:
            self.assertIn(
                prop, all_props, f"Expected property {prop} not found in index keys"
            )

    def test_non_vevent_components_dont_include_rrule(self):
        """Test that non-VEVENT components don't include RRULE in their index keys."""
        # Test VTODO time range matcher
        matcher = ComponentTimeRangeMatcher(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2020, 1, 2, tzinfo=timezone.utc),
            comp="VTODO",
        )

        index_keys = matcher.index_keys()

        # Should NOT include RRULE for VTODO
        all_props = []
        for key_set in index_keys:
            all_props.extend(key_set)

        self.assertNotIn(
            "P=RRULE", all_props, "VTODO time-range filter should not include RRULE"
        )

    def test_rrule_expansion_boundaries(self):
        """Test that RRULE expansion respects time range boundaries correctly."""
        cal = ICalendarFile([RRULE_VEVENT], "text/calendar")

        # Test various time ranges to ensure proper boundary handling
        test_cases = [
            # (start, end, should_match, description)
            (
                datetime(2019, 12, 30),
                datetime(2020, 1, 2),
                True,
                "Should match first occurrence",
            ),
            (
                datetime(2020, 1, 7),
                datetime(2020, 1, 9),
                True,
                "Should match second occurrence",
            ),
            (
                datetime(2020, 1, 14),
                datetime(2020, 1, 16),
                True,
                "Should match third occurrence",
            ),
            (
                datetime(2020, 1, 21),
                datetime(2020, 1, 23),
                True,
                "Should match fourth occurrence",
            ),
            (
                datetime(2020, 1, 28),
                datetime(2020, 1, 30),
                True,
                "Should match fifth occurrence",
            ),
            (
                datetime(2020, 2, 4),
                datetime(2020, 2, 6),
                False,
                "Should not match after COUNT=5",
            ),
            (
                datetime(2019, 12, 20),
                datetime(2019, 12, 25),
                False,
                "Should not match before first occurrence",
            ),
        ]

        for start, end, should_match, description in test_cases:
            with self.subTest(description=description):
                filter = CalendarFilter(timezone.utc)
                comp_filter = ComponentFilter("VCALENDAR")
                event_filter = ComponentFilter("VEVENT")
                event_filter.time_range = ComponentTimeRangeMatcher(
                    start.replace(tzinfo=timezone.utc),
                    end.replace(tzinfo=timezone.utc),
                    comp="VEVENT",
                )
                comp_filter.children.append(event_filter)
                filter.children.append(comp_filter)

                keys = []
                for key_set in filter.index_keys():
                    keys.extend(key_set)

                indexes = cal.get_indexes(keys)
                result = filter.check_from_indexes("test.ics", indexes)

                self.assertEqual(
                    result,
                    should_match,
                    f"{description}: expected {should_match}, got {result}",
                )


if __name__ == "__main__":
    unittest.main()
