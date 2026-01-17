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

"""Comprehensive filter combination tests for CalDAV calendar-query (RFC 4791 §9.7)."""

import unittest
from datetime import datetime, timezone

from xandikos.icalendar import CalendarFilter, ICalendarFile


class CalDAVFilterCombinationTests(unittest.TestCase):
    """Test various combinations of CalDAV filters (RFC 4791 Section 9.7)."""

    def setUp(self):
        """Set up test calendar data."""
        # Test event 1: Meeting with location
        self.event1 = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VEVENT\r\n",
                b"UID:event1@example.com\r\n",
                b"DTSTART:20260115T100000Z\r\n",
                b"DTEND:20260115T110000Z\r\n",
                b"SUMMARY:Team Meeting\r\n",
                b"LOCATION:Conference Room A\r\n",
                b"END:VEVENT\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

        # Test event 2: All-day event without location
        self.event2 = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VEVENT\r\n",
                b"UID:event2@example.com\r\n",
                b"DTSTART;VALUE=DATE:20260116\r\n",
                b"SUMMARY:Holiday\r\n",
                b"END:VEVENT\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

        # Test event 3: Event with attendees
        self.event3 = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VEVENT\r\n",
                b"UID:event3@example.com\r\n",
                b"DTSTART:20260117T140000Z\r\n",
                b"DTEND:20260117T150000Z\r\n",
                b"SUMMARY:Project Review\r\n",
                b"ATTENDEE:mailto:user1@example.com\r\n",
                b"ATTENDEE;PARTSTAT=ACCEPTED:mailto:user2@example.com\r\n",
                b"END:VEVENT\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

        # Test todo
        self.todo1 = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VTODO\r\n",
                b"UID:todo1@example.com\r\n",
                b"SUMMARY:Fix bug\r\n",
                b"PRIORITY:1\r\n",
                b"END:VTODO\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

    def test_comp_filter_vevent_only(self):
        """Test comp-filter for VEVENT components only.

        RFC 4791 Section 9.7.1: Component filter matches components of specified type.
        """
        filter_obj = CalendarFilter(None)
        filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent("VEVENT")

        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        self.assertTrue(filter_obj.check("event2.ics", self.event2))
        self.assertTrue(filter_obj.check("event3.ics", self.event3))
        self.assertFalse(filter_obj.check("todo1.ics", self.todo1))

    def test_comp_filter_vtodo_only(self):
        """Test comp-filter for VTODO components only."""
        filter_obj = CalendarFilter(None)
        filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent("VTODO")

        self.assertFalse(filter_obj.check("event1.ics", self.event1))
        self.assertTrue(filter_obj.check("todo1.ics", self.todo1))

    def test_prop_filter_summary_contains(self):
        """Test prop-filter with text-match contains.

        RFC 4791 Section 9.7.5: Text match with contains.
        Note: Current implementation only supports contains matching.
        """
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
            .filter_text_match("Meeting", collation="i;unicode-casemap")
        )

        # Event1 has "Team Meeting"
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2 has "Holiday" - no match
        self.assertFalse(filter_obj.check("event2.ics", self.event2))

    def test_prop_filter_summary_exact_word(self):
        """Test prop-filter with text-match for exact word.

        Note: Current implementation only supports contains matching.
        """
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
            .filter_text_match("Holiday", collation="i;unicode-casemap")
        )

        self.assertFalse(filter_obj.check("event1.ics", self.event1))
        self.assertTrue(filter_obj.check("event2.ics", self.event2))

    def test_prop_filter_is_not_defined(self):
        """Test prop-filter with is-not-defined.

        RFC 4791 Section 9.7.3: Property must not exist.
        """
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("LOCATION", is_not_defined=True)
        )

        # Event1 has LOCATION
        self.assertFalse(filter_obj.check("event1.ics", self.event1))
        # Event2 has no LOCATION
        self.assertTrue(filter_obj.check("event2.ics", self.event2))

    def test_prop_filter_is_defined(self):
        """Test prop-filter without is-not-defined (property must exist)."""
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("LOCATION")
        )

        # Event1 has LOCATION
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2 has no LOCATION
        self.assertFalse(filter_obj.check("event2.ics", self.event2))

    def test_time_range_filter_overlap(self):
        """Test time-range filter for overlapping events.

        RFC 4791 Section 9.9: Time range matching.
        """
        filter_obj = CalendarFilter(timezone.utc)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_time_range(
                start=datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 16, 0, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Event1 is on 2026-01-15 10:00-11:00
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2 is all-day 2026-01-16 (outside range end)
        self.assertFalse(filter_obj.check("event2.ics", self.event2))
        # Event3 is on 2026-01-17 (outside range)
        self.assertFalse(filter_obj.check("event3.ics", self.event3))

    def test_combined_comp_and_prop_filter(self):
        """Test combination of comp-filter and prop-filter.

        RFC 4791 Section 9.7: Filters can be combined.
        """
        filter_obj = CalendarFilter(None)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Review", collation="i;unicode-casemap"
        )
        comp_filter.filter_property("ATTENDEE")

        # Event1: has "Meeting" not "Review", has no attendees
        self.assertFalse(filter_obj.check("event1.ics", self.event1))
        # Event3: has "Review" and has attendees
        self.assertTrue(filter_obj.check("event3.ics", self.event3))

    def test_combined_comp_and_time_range(self):
        """Test combination of comp-filter and time-range."""
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_time_range(
            start=datetime(2026, 1, 14, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 18, 0, 0, 0, tzinfo=timezone.utc),
        )
        comp_filter.filter_property("LOCATION")

        # Event1: in time range, has location
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2: in time range, no location
        self.assertFalse(filter_obj.check("event2.ics", self.event2))
        # Event3: in time range, no location
        self.assertFalse(filter_obj.check("event3.ics", self.event3))

    def test_prop_filter_attendee_exists(self):
        """Test prop-filter checking if ATTENDEE exists.

        RFC 4791 Section 9.7.2: Property existence filtering.
        """
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("ATTENDEE")
        )

        # Event1: no attendees
        self.assertFalse(filter_obj.check("event1.ics", self.event1))
        # Event3: has attendees
        self.assertTrue(filter_obj.check("event3.ics", self.event3))

    def test_multiple_prop_filters_and_logic(self):
        """Test multiple prop-filters (AND logic by default).

        RFC 4791 Section 9.7.2: Multiple filters use AND logic.
        """
        filter_obj = CalendarFilter(None)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Meeting", collation="i;unicode-casemap"
        )
        comp_filter.filter_property("LOCATION").filter_text_match(
            "Conference", collation="i;unicode-casemap"
        )

        # Event1: has "Meeting" AND "Conference Room A"
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2: no match
        self.assertFalse(filter_obj.check("event2.ics", self.event2))

    def test_text_match_case_insensitive(self):
        """Test text-match with case insensitivity.

        RFC 4791 Section 9.7.5: Collation determines case sensitivity.
        """
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
            .filter_text_match("MEETING", collation="i;unicode-casemap")
        )

        # Event1 has "Team Meeting" - should match with case-insensitive
        self.assertTrue(filter_obj.check("event1.ics", self.event1))

    def test_text_match_substring(self):
        """Test text-match with substring matching."""
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
            .filter_text_match("Team", collation="i;unicode-casemap")
        )

        # Event1: "Team Meeting" contains "Team"
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2: "Holiday" doesn't contain "Team"
        self.assertFalse(filter_obj.check("event2.ics", self.event2))

    def test_text_match_word_in_text(self):
        """Test text-match finding word within text."""
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
            .filter_text_match("Review", collation="i;unicode-casemap")
        )

        # Event3: "Project Review" contains "Review"
        self.assertTrue(filter_obj.check("event3.ics", self.event3))
        # Event1: "Team Meeting" doesn't contain "Review"
        self.assertFalse(filter_obj.check("event1.ics", self.event1))

    def test_empty_comp_filter(self):
        """Test comp-filter with no sub-filters matches any component of that type."""
        filter_obj = CalendarFilter(None)
        filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent("VEVENT")

        # Should match all VEVENTs
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        self.assertTrue(filter_obj.check("event2.ics", self.event2))
        self.assertTrue(filter_obj.check("event3.ics", self.event3))
        # Should not match VTODO
        self.assertFalse(filter_obj.check("todo1.ics", self.todo1))

    def test_time_range_future_events(self):
        """Test time-range filter for future events.

        RFC 4791 Section 9.9: Time range with distant future end.
        """
        filter_obj = CalendarFilter(timezone.utc)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_time_range(
                start=datetime(2026, 1, 16, 0, 0, 0, tzinfo=timezone.utc),
                end=datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Event1: 2026-01-15 (before start)
        self.assertFalse(filter_obj.check("event1.ics", self.event1))
        # Event2: 2026-01-16 (on or after start)
        self.assertTrue(filter_obj.check("event2.ics", self.event2))
        # Event3: 2026-01-17 (after start)
        self.assertTrue(filter_obj.check("event3.ics", self.event3))

    def test_negate_with_is_not_defined(self):
        """Test negation using is-not-defined."""
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("ATTENDEE", is_not_defined=True)
        )

        # Event1: no attendees - should match
        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        # Event2: no attendees - should match
        self.assertTrue(filter_obj.check("event2.ics", self.event2))
        # Event3: has attendees - should not match
        self.assertFalse(filter_obj.check("event3.ics", self.event3))

    def test_text_match_equals(self):
        """Test SUMMARY text-match with equals match type."""
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Team Meeting", collation="i;unicode-casemap", match_type="equals"
        )

        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        self.assertFalse(filter_obj.check("event2.ics", self.event2))
        self.assertFalse(filter_obj.check("event3.ics", self.event3))

    def test_text_match_starts_with(self):
        """Test SUMMARY text-match with starts-with match type."""
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Team", collation="i;unicode-casemap", match_type="starts-with"
        )

        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        self.assertFalse(filter_obj.check("event2.ics", self.event2))
        self.assertFalse(filter_obj.check("event3.ics", self.event3))

    def test_text_match_ends_with(self):
        """Test SUMMARY text-match with ends-with match type."""
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Meeting", collation="i;unicode-casemap", match_type="ends-with"
        )

        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        self.assertFalse(filter_obj.check("event2.ics", self.event2))
        self.assertFalse(filter_obj.check("event3.ics", self.event3))

    def test_text_match_contains_default(self):
        """Test SUMMARY text-match with default contains match type."""
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        # Default should be contains
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Meeting", collation="i;unicode-casemap"
        )

        self.assertTrue(filter_obj.check("event1.ics", self.event1))
        self.assertFalse(filter_obj.check("event2.ics", self.event2))
        self.assertFalse(filter_obj.check("event3.ics", self.event3))


class CalDAVFilterEdgeCasesTests(unittest.TestCase):
    """Test edge cases for CalDAV filters."""

    def test_filter_with_unicode_in_summary(self):
        """Test filtering events with Unicode characters."""
        event = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VEVENT\r\n",
                b"UID:unicode@example.com\r\n",
                b"DTSTART:20260115T100000Z\r\n",
                b"SUMMARY:Caf\xc3\xa9 Meeting\r\n",
                b"END:VEVENT\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
            .filter_text_match("Café", collation="i;unicode-casemap")
        )
        self.assertTrue(filter_obj.check("event.ics", event))

    def test_filter_with_empty_property(self):
        """Test filtering when property exists but is empty."""
        event = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VEVENT\r\n",
                b"UID:empty@example.com\r\n",
                b"DTSTART:20260115T100000Z\r\n",
                b"SUMMARY:\r\n",
                b"END:VEVENT\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

        # Property is defined (even if empty)
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("SUMMARY")
        )
        self.assertTrue(filter_obj.check("event.ics", event))

    def test_filter_description_property(self):
        """Test filtering on DESCRIPTION property."""
        event = ICalendarFile(
            [
                b"BEGIN:VCALENDAR\r\n",
                b"VERSION:2.0\r\n",
                b"BEGIN:VEVENT\r\n",
                b"UID:desc@example.com\r\n",
                b"DTSTART:20260115T100000Z\r\n",
                b"SUMMARY:Meeting\r\n",
                b"DESCRIPTION:Quarterly review with stakeholders\r\n",
                b"END:VEVENT\r\n",
                b"END:VCALENDAR\r\n",
            ],
            "text/calendar",
        )

        # Should match text in DESCRIPTION
        filter_obj = CalendarFilter(None)
        (
            filter_obj.filter_subcomponent("VCALENDAR")
            .filter_subcomponent("VEVENT")
            .filter_property("DESCRIPTION")
            .filter_text_match("review", collation="i;unicode-casemap")
        )
        self.assertTrue(filter_obj.check("event.ics", event))


if __name__ == "__main__":
    unittest.main()
