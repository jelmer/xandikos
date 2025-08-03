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

"""Tests for xandikos.web."""

import os
import shutil
import tempfile
import unittest

from .. import caldav
from ..icalendar import ICalendarFile
from ..store.git import TreeGitStore
from ..web import CalendarCollection, XandikosBackend

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
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""


class CalendarCollectionTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        self.store = TreeGitStore.create(os.path.join(self.tempdir, "c"))
        self.store.load_extra_file_handler(ICalendarFile)
        self.backend = XandikosBackend(self.tempdir)

        self.cal = CalendarCollection(self.backend, "c", self.store)

    def test_description(self):
        self.store.set_description("foo")
        self.assertEqual("foo", self.cal.get_calendar_description())

    def test_color(self):
        self.assertRaises(KeyError, self.cal.get_calendar_color)
        self.cal.set_calendar_color("#aabbcc")
        self.assertEqual("#aabbcc", self.cal.get_calendar_color())

    def test_get_supported_calendar_components(self):
        self.assertEqual(
            ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY"],
            self.cal.get_supported_calendar_components(),
        )

    def test_calendar_query_vtodos(self):
        def create_fn(cls):
            f = cls(None)
            f.filter_subcomponent("VCALENDAR").filter_subcomponent("VTODO")
            return f

        self.assertEqual([], list(self.cal.calendar_query(create_fn)))
        self.store.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        result = list(self.cal.calendar_query(create_fn))
        self.assertEqual(1, len(result))
        self.assertEqual("foo.ics", result[0][0])
        self.assertIs(self.store, result[0][1].store)
        self.assertEqual("foo.ics", result[0][1].name)
        self.assertEqual("text/calendar", result[0][1].content_type)

    def test_calendar_query_vtodo_by_uid(self):
        def create_fn(cls):
            f = cls(None)
            f.filter_subcomponent("VCALENDAR").filter_subcomponent(
                "VTODO"
            ).filter_property("UID").filter_text_match(
                "bdc22720-b9e1-42c9-89c2-a85405d8fbff"
            )
            return f

        self.assertEqual([], list(self.cal.calendar_query(create_fn)))
        self.store.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        result = list(self.cal.calendar_query(create_fn))
        self.assertEqual(1, len(result))
        self.assertEqual("foo.ics", result[0][0])
        self.assertIs(self.store, result[0][1].store)
        self.assertEqual("foo.ics", result[0][1].name)
        self.assertEqual("text/calendar", result[0][1].content_type)

    def test_get_supported_calendar_data_types(self):
        self.assertEqual(
            [("text/calendar", "1.0"), ("text/calendar", "2.0")],
            self.cal.get_supported_calendar_data_types(),
        )

    def test_get_max_date_time(self):
        self.assertEqual("99991231T235959Z", self.cal.get_max_date_time())

    def test_get_min_date_time(self):
        self.assertEqual("00010101T000000Z", self.cal.get_min_date_time())

    def test_members(self):
        self.assertEqual([], list(self.cal.members()))
        self.store.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        result = list(self.cal.members())
        self.assertEqual(1, len(result))
        self.assertEqual("foo.ics", result[0][0])
        self.assertIs(self.store, result[0][1].store)
        self.assertEqual("foo.ics", result[0][1].name)
        self.assertEqual("text/calendar", result[0][1].content_type)

    def test_get_member(self):
        self.assertRaises(KeyError, self.cal.get_member, "foo.ics")
        self.store.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        result = self.cal.get_member("foo.ics")
        self.assertIs(self.store, result.store)
        self.assertEqual("foo.ics", result.name)
        self.assertEqual("text/calendar", result.content_type)

    def test_delete_member(self):
        self.assertRaises(KeyError, self.cal.get_member, "foo.ics")
        self.store.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.cal.get_member("foo.ics")
        self.cal.delete_member("foo.ics")
        self.assertRaises(KeyError, self.cal.get_member, "foo.ics")

    def test_get_schedule_calendar_transparency(self):
        self.assertEqual(
            caldav.TRANSPARENCY_OPAQUE,
            self.cal.get_schedule_calendar_transparency(),
        )

    def test_git_refs(self):
        from ..web import XandikosApp
        from wsgiref.util import setup_testing_defaults

        self.store.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        app = XandikosApp(self.backend, "user")

        default_branch = self.store.repo.refs.follow(b"HEAD")[0][-1]
        commit_hash = self.store.repo.refs[default_branch]

        environ = {
            "PATH_INFO": "/c/.git/info/refs",
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": "",
        }
        setup_testing_defaults(environ)

        codes = []

        def start_response(code, _headers):
            codes.append(code)

        body = b"".join(app(environ, start_response))

        self.assertEqual(["200 OK"], codes)
        self.assertEqual(b"".join([commit_hash, b"\t", default_branch, b"\n"]), body)

    def test_calendar_availability_not_set(self):
        """Test getting availability when none is set raises KeyError."""
        with self.assertRaises(KeyError):
            self.cal.get_calendar_availability()

    def test_calendar_availability_set_and_get(self):
        """Test setting and getting calendar availability."""
        availability_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VAVAILABILITY
DTSTART:20240101T090000Z
DTEND:20240101T170000Z
BUSYTYPE:BUSY-UNAVAILABLE
SUMMARY:Working hours
END:VAVAILABILITY
END:VCALENDAR"""

        # Set availability
        self.cal.set_calendar_availability(availability_data)

        # Get it back - it will be in normalized form
        retrieved = self.cal.get_calendar_availability()

        # Verify we can parse both and they represent the same data
        from icalendar.cal import Calendar as ICalendar

        original_cal = ICalendar.from_ical(availability_data)
        retrieved_cal = ICalendar.from_ical(retrieved)

        # Compare the normalized forms
        self.assertEqual(original_cal.to_ical(), retrieved_cal.to_ical())

    def test_calendar_availability_set_none_removes(self):
        """Test that setting availability to None removes it."""
        availability_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VAVAILABILITY
DTSTART:20240101T090000Z
DTEND:20240101T170000Z
BUSYTYPE:BUSY
END:VAVAILABILITY
END:VCALENDAR"""

        # Set availability first
        self.cal.set_calendar_availability(availability_data)

        # Verify it was stored
        retrieved = self.cal.get_calendar_availability()
        self.assertIsNotNone(retrieved)

        # Remove it
        self.cal.set_calendar_availability(None)

        # Should raise KeyError now
        with self.assertRaises(KeyError):
            self.cal.get_calendar_availability()

    def test_calendar_availability_invalid_data(self):
        """Test that setting invalid iCalendar data raises InvalidFileContents."""
        from ..store import InvalidFileContents

        invalid_data = "This is not valid iCalendar data"

        with self.assertRaises(InvalidFileContents) as cm:
            self.cal.set_calendar_availability(invalid_data)

        # Check the exception has the expected attributes
        self.assertEqual(cm.exception.content_type, "text/calendar")
        self.assertEqual(cm.exception.data, invalid_data)
        self.assertIsInstance(cm.exception.error, ValueError)

    def test_calendar_availability_remove_nonexistent(self):
        """Test that removing non-existent availability doesn't raise errors."""
        # Should not raise any exception
        self.cal.set_calendar_availability(None)

        # Still should raise KeyError when trying to get
        with self.assertRaises(KeyError):
            self.cal.get_calendar_availability()

    def test_calendar_availability_update(self):
        """Test updating existing availability data."""
        availability1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VAVAILABILITY
DTSTART:20240101T090000Z
DTEND:20240101T170000Z
BUSYTYPE:BUSY-UNAVAILABLE
SUMMARY:Working hours v1
END:VAVAILABILITY
END:VCALENDAR"""

        availability2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VAVAILABILITY
DTSTART:20240101T080000Z
DTEND:20240101T180000Z
BUSYTYPE:BUSY
SUMMARY:Working hours v2
BEGIN:AVAILABLE
DTSTART:20240101T120000Z
DTEND:20240101T130000Z
SUMMARY:Lunch break
END:AVAILABLE
END:VAVAILABILITY
END:VCALENDAR"""

        # Set first version
        self.cal.set_calendar_availability(availability1)

        # Verify first version was stored
        retrieved1 = self.cal.get_calendar_availability()
        from icalendar.cal import Calendar as ICalendar

        original1_cal = ICalendar.from_ical(availability1)
        retrieved1_cal = ICalendar.from_ical(retrieved1)
        self.assertEqual(original1_cal.to_ical(), retrieved1_cal.to_ical())

        # Update to second version
        self.cal.set_calendar_availability(availability2)

        # Verify second version was stored
        retrieved2 = self.cal.get_calendar_availability()
        original2_cal = ICalendar.from_ical(availability2)
        retrieved2_cal = ICalendar.from_ical(retrieved2)
        self.assertEqual(original2_cal.to_ical(), retrieved2_cal.to_ical())
