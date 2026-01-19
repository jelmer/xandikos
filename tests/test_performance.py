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

"""Performance tests for large collections (RFC 4918, RFC 4791, RFC 6352).

These tests ensure that Xandikos performs adequately with large collections
of calendar events and contacts.
"""

import time
import unittest
from datetime import datetime, timedelta, timezone

from xandikos.icalendar import CalendarFilter, ICalendarFile
from xandikos.vcard import CardDAVFilter, VCardFile


class LargeCollectionPerformanceTests(unittest.TestCase):
    """Performance tests for large collections."""

    def setUp(self):
        """Set up large test collections."""
        # Create a large CalDAV calendar (500 events)
        self.large_calendar_events = []
        base_date = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(500):
            event_date = base_date + timedelta(days=i)
            event = ICalendarFile(
                [
                    b"BEGIN:VCALENDAR\r\n",
                    b"VERSION:2.0\r\n",
                    b"PRODID:-//Test//Test//EN\r\n",
                    b"BEGIN:VEVENT\r\n",
                    f"UID:event-{i}@test.example.com\r\n".encode(),
                    f"DTSTART:{event_date.strftime('%Y%m%dT%H%M%SZ')}\r\n".encode(),
                    f"DTEND:{(event_date + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}\r\n".encode(),
                    f"SUMMARY:Event {i}\r\n".encode(),
                    b"END:VEVENT\r\n",
                    b"END:VCALENDAR\r\n",
                ],
                "text/calendar",
            )
            self.large_calendar_events.append((f"event-{i}.ics", event))

        # Create a large CardDAV addressbook (500 contacts)
        self.large_addressbook_contacts = []
        for i in range(500):
            vcard = VCardFile(
                [
                    b"BEGIN:VCARD\r\n",
                    b"VERSION:3.0\r\n",
                    f"FN:Contact {i}\r\n".encode(),
                    f"N:Contact{i};Test;;;\r\n".encode(),
                    f"EMAIL:contact{i}@example.com\r\n".encode(),
                    f"TEL:+1-555-{i:04d}\r\n".encode(),
                    b"END:VCARD\r\n",
                ],
                "text/vcard",
            )
            self.large_addressbook_contacts.append((f"contact-{i}.vcf", vcard))

    def test_caldav_filter_performance_no_match(self):
        """Test CalDAV filter performance on large calendar (no matches).

        This tests worst-case performance where the filter must check
        all events but finds no matches.
        """
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "NonexistentEvent", collation="i;unicode-casemap"
        )

        start_time = time.perf_counter()
        matches = [
            name
            for name, event in self.large_calendar_events
            if filter_obj.check(name, event)
        ]
        elapsed = time.perf_counter() - start_time

        self.assertEqual(0, len(matches))
        # Should complete in under 5 seconds for 500 events
        self.assertLess(elapsed, 5.0, f"Filter took {elapsed:.2f}s, expected < 5s")

    def test_caldav_filter_performance_some_matches(self):
        """Test CalDAV filter performance with partial matches.

        This tests typical performance where some events match the filter.
        """
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        # Match events with "Event 1" in summary (Event 1, Event 10-19, Event 100-199)
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Event 1", collation="i;unicode-casemap"
        )

        start_time = time.perf_counter()
        matches = [
            name
            for name, event in self.large_calendar_events
            if filter_obj.check(name, event)
        ]
        elapsed = time.perf_counter() - start_time

        # Should find "Event 1", "Event 10"-"Event 19", "Event 100"-"Event 199"
        self.assertGreater(len(matches), 100)
        self.assertLess(elapsed, 5.0, f"Filter took {elapsed:.2f}s, expected < 5s")

    def test_caldav_time_range_filter_performance(self):
        """Test CalDAV time-range filter performance.

        This tests performance of time-range queries, which are common
        in calendar applications.
        """
        filter_obj = CalendarFilter(timezone.utc)
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )
        # Query for events in January 2025 (first 31 events)
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 2, 1, tzinfo=timezone.utc)
        comp_filter.filter_time_range(start, end)

        start_time = time.perf_counter()
        matches = [
            name
            for name, event in self.large_calendar_events
            if filter_obj.check(name, event)
        ]
        elapsed = time.perf_counter() - start_time

        # Should find 31 events (January has 31 days)
        self.assertEqual(31, len(matches))
        self.assertLess(elapsed, 5.0, f"Filter took {elapsed:.2f}s, expected < 5s")

    def test_carddav_filter_performance_no_match(self):
        """Test CardDAV filter performance on large addressbook (no matches).

        This tests worst-case performance where the filter must check
        all contacts but finds no matches.
        """
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "NonexistentContact", match_type="contains"
        )

        start_time = time.perf_counter()
        matches = [
            name
            for name, vcard in self.large_addressbook_contacts
            if filter_obj.check(name, vcard)
        ]
        elapsed = time.perf_counter() - start_time

        self.assertEqual(0, len(matches))
        # Should complete in under 2 seconds for 500 contacts
        self.assertLess(elapsed, 2.0, f"Filter took {elapsed:.2f}s, expected < 2s")

    def test_carddav_filter_performance_some_matches(self):
        """Test CardDAV filter performance with partial matches.

        This tests typical performance where some contacts match the filter.
        """
        filter_obj = CardDAVFilter()
        # Match contacts with "Contact 1" in FN
        filter_obj.add_property_filter("FN").add_text_match(
            "Contact 1", match_type="contains"
        )

        start_time = time.perf_counter()
        matches = [
            name
            for name, vcard in self.large_addressbook_contacts
            if filter_obj.check(name, vcard)
        ]
        elapsed = time.perf_counter() - start_time

        # Should find "Contact 1", "Contact 10"-"Contact 19", "Contact 100"-"Contact 199"
        self.assertGreater(len(matches), 100)
        self.assertLess(elapsed, 2.0, f"Filter took {elapsed:.2f}s, expected < 2s")

    def test_carddav_email_filter_performance(self):
        """Test CardDAV email filter performance.

        This tests performance of email-based queries, which are common
        in addressbook applications.
        """
        filter_obj = CardDAVFilter()
        # Match contacts with specific email domain
        filter_obj.add_property_filter("EMAIL").add_text_match(
            "example.com", match_type="contains"
        )

        start_time = time.perf_counter()
        matches = [
            name
            for name, vcard in self.large_addressbook_contacts
            if filter_obj.check(name, vcard)
        ]
        elapsed = time.perf_counter() - start_time

        # All contacts should match (all have @example.com)
        self.assertEqual(500, len(matches))
        self.assertLess(elapsed, 2.0, f"Filter took {elapsed:.2f}s, expected < 2s")

    def test_caldav_complex_filter_performance(self):
        """Test CalDAV complex filter with multiple conditions.

        This tests performance of complex queries with multiple filter
        conditions combined.
        """
        filter_obj = CalendarFilter(timezone.utc)
        filter_obj.test = all  # AND logic
        comp_filter = filter_obj.filter_subcomponent("VCALENDAR").filter_subcomponent(
            "VEVENT"
        )

        # Multiple conditions: text match + time range
        comp_filter.filter_property("SUMMARY").filter_text_match(
            "Event", collation="i;unicode-casemap"
        )
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 2, 1, tzinfo=timezone.utc)
        comp_filter.filter_time_range(start, end)

        start_time = time.perf_counter()
        matches = [
            name
            for name, event in self.large_calendar_events
            if filter_obj.check(name, event)
        ]
        elapsed = time.perf_counter() - start_time

        # Should find 31 events in January
        self.assertEqual(31, len(matches))
        self.assertLess(elapsed, 5.0, f"Filter took {elapsed:.2f}s, expected < 5s")

    def test_carddav_complex_filter_performance(self):
        """Test CardDAV complex filter with multiple conditions.

        This tests performance of complex queries with multiple filter
        conditions combined.
        """
        filter_obj = CardDAVFilter()
        filter_obj.test = all  # AND logic
        filter_obj.add_property_filter("EMAIL")
        filter_obj.add_property_filter("TEL")
        filter_obj.add_property_filter("FN").add_text_match(
            "Contact 1", match_type="contains"
        )

        start_time = time.perf_counter()
        matches = [
            name
            for name, vcard in self.large_addressbook_contacts
            if filter_obj.check(name, vcard)
        ]
        elapsed = time.perf_counter() - start_time

        # Should find contacts matching all conditions
        self.assertGreater(len(matches), 100)
        self.assertLess(elapsed, 2.0, f"Filter took {elapsed:.2f}s, expected < 2s")


if __name__ == "__main__":
    unittest.main()
