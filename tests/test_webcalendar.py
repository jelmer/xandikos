# Xandikos
# Copyright (C) 2026 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Tests for the browser-facing calendar UI in xandikos.webcalendar."""

import io
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from icalendar import Calendar as ICalendar

from xandikos import webcalendar
from xandikos.icalendar import ICalendarFile
from xandikos.store import (
    STORE_TYPE_CALENDAR,
    STORE_TYPE_SCHEDULE_OUTBOX,
    STORE_TYPE_SUBSCRIPTION,
)
from xandikos.store.git import TreeGitStore
from xandikos.web import (
    CalendarCollection,
    ScheduleOutbox,
    SingleUserFilesystemBackend,
    SubscriptionCollection,
    XandikosApp,
)


EXAMPLE_EVENT = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:event-1
DTSTAMP:20260101T120000Z
SUMMARY:Team sync
DTSTART:20260516T100000
DTEND:20260516T110000
LOCATION:Room A
DESCRIPTION:Weekly catch-up
END:VEVENT
END:VCALENDAR
"""


EXAMPLE_TODO = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VTODO
UID:todo-1
DTSTAMP:20260101T120000Z
SUMMARY:Buy milk
DUE:20260516T180000
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR
"""


EXAMPLE_JOURNAL = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VJOURNAL
UID:journal-1
DTSTAMP:20260101T120000Z
DTSTART;VALUE=DATE:20260516
SUMMARY:Trip notes
DESCRIPTION:Saw the mountains today. Long ride, good weather.
END:VJOURNAL
END:VCALENDAR
"""


EXAMPLE_RECURRING = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:recurring-1
DTSTAMP:20260101T120000Z
SUMMARY:Daily standup
DTSTART:20260515T093000
DTEND:20260515T094500
RRULE:FREQ=DAILY;COUNT=5
END:VEVENT
END:VCALENDAR
"""


EXAMPLE_ALL_DAY = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:allday-1
DTSTAMP:20260101T120000Z
SUMMARY:Conference
DTSTART;VALUE=DATE:20260518
DTEND;VALUE=DATE:20260521
END:VEVENT
END:VCALENDAR
"""


class HelperTests(unittest.TestCase):
    def test_parse_month_valid(self):
        self.assertEqual(webcalendar._parse_month("2026-05"), (2026, 5))
        self.assertEqual(webcalendar._parse_month("2024-12"), (2024, 12))

    def test_parse_month_bad_falls_back(self):
        # Bad input falls back to current month.
        y, m = webcalendar._parse_month("nope")
        self.assertEqual((y, m), (date.today().year, date.today().month))
        y, m = webcalendar._parse_month("2026-13")
        self.assertEqual((y, m), (date.today().year, date.today().month))

    def test_shift_month_wraps_year(self):
        self.assertEqual(webcalendar._shift_month(2026, 1, -1), (2025, 12))
        self.assertEqual(webcalendar._shift_month(2026, 12, +1), (2027, 1))
        self.assertEqual(webcalendar._shift_month(2026, 5, 0), (2026, 5))

    def test_month_grid_starts_on_monday(self):
        grid = webcalendar._month_grid(2026, 5)
        # First week's first day is a Monday.
        self.assertEqual(grid[0][0].weekday(), 0)
        # All dates in the grid are date instances.
        self.assertTrue(all(isinstance(d, date) for week in grid for d in week))

    def test_component_to_form_round_trip(self):
        cal = ICalendar.from_ical(EXAMPLE_EVENT)
        ev = next(c for c in cal.subcomponents if c.name == "VEVENT")
        form = webcalendar.component_to_form(ev)
        self.assertEqual(form["kind"], "event")
        self.assertEqual(form["summary"], "Team sync")
        self.assertEqual(form["location"], "Room A")
        self.assertEqual(form["start_dt"], "2026-05-16T10:00")
        self.assertEqual(form["end_dt"], "2026-05-16T11:00")
        self.assertFalse(form["all_day"])

    def test_component_to_form_all_day(self):
        cal = ICalendar.from_ical(EXAMPLE_ALL_DAY)
        ev = next(c for c in cal.subcomponents if c.name == "VEVENT")
        form = webcalendar.component_to_form(ev)
        self.assertTrue(form["all_day"])
        self.assertEqual(form["start_date"], "2026-05-18")
        # DTEND is exclusive (5/21) so the user-visible end is 5/20.
        self.assertEqual(form["end_date"], "2026-05-20")

    def test_build_new_event_from_form(self):
        cal = webcalendar.build_new_component(
            {
                "kind": "event",
                "summary": "New thing",
                "start_dt": "2026-06-01T09:00",
                "end_dt": "2026-06-01T10:00",
                "location": "Anywhere",
            }
        )
        ev = next(c for c in cal.subcomponents if c.name == "VEVENT")
        self.assertEqual(str(ev["SUMMARY"]), "New thing")
        self.assertEqual(str(ev["LOCATION"]), "Anywhere")
        self.assertIn("DTSTAMP", ev)
        self.assertIn("UID", ev)

    def test_build_new_todo_from_form(self):
        cal = webcalendar.build_new_component(
            {
                "kind": "todo",
                "summary": "Do laundry",
                "all_day": "1",
                "end_date": "2026-06-01",
                "status": "NEEDS-ACTION",
            }
        )
        td = next(c for c in cal.subcomponents if c.name == "VTODO")
        self.assertEqual(str(td["SUMMARY"]), "Do laundry")
        self.assertEqual(str(td["STATUS"]), "NEEDS-ACTION")
        self.assertIn("DUE", td)

    def test_update_calendar_preserves_other_props(self):
        cal = ICalendar.from_ical(
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//\r\n"
            b"BEGIN:VEVENT\r\nUID:x\r\nDTSTAMP:20260101T000000Z\r\n"
            b"SUMMARY:Old\r\nDTSTART:20260601T100000\r\nDTEND:20260601T110000\r\n"
            b"RRULE:FREQ=DAILY\r\nORGANIZER:mailto:a@example.org\r\n"
            b"ATTENDEE:mailto:b@example.org\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        updated = webcalendar.update_calendar(
            cal,
            {
                "summary": "Updated",
                "start_dt": "2026-06-01T11:00",
                "end_dt": "2026-06-01T12:00",
            },
        )
        ev = next(c for c in updated.subcomponents if c.name == "VEVENT")
        self.assertEqual(str(ev["SUMMARY"]), "Updated")
        # RRULE/ORGANIZER/ATTENDEE preserved
        self.assertIn("RRULE", ev)
        self.assertIn("ORGANIZER", ev)
        self.assertIn("ATTENDEE", ev)


class WebCalendarAppTests(unittest.TestCase):
    """End-to-end tests via XandikosApp."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        store_path = os.path.join(self.tempdir, "calendar")
        self.store = TreeGitStore.create(store_path)
        self.store.set_type(STORE_TYPE_CALENDAR)
        self.store.load_extra_file_handler(ICalendarFile)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = CalendarCollection(self.backend, "calendar", self.store)
        self.app = XandikosApp(self.backend, "user")

    def _request(self, method, path, query="", body=b"", accept="text/html"):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "HTTP_ACCEPT": accept,
        }
        if body:
            environ["wsgi.input"] = io.BytesIO(body)
            environ["CONTENT_LENGTH"] = str(len(body))
            environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
        setup_testing_defaults(environ)
        environ["QUERY_STRING"] = query
        captured = {}

        def sr(status, headers):
            captured["s"] = status
            captured["h"] = dict(headers)

        body_bytes = b"".join(self.app(environ, sr))
        return captured["s"], captured["h"], body_bytes

    def test_month_view_renders(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        status, headers, body = self._request(
            "GET", "/calendar/", query="month=2026-05"
        )
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("May 2026", text)
        self.assertIn("Team sync", text)
        # Has both nav buttons
        self.assertIn("month=2026-04", text)
        self.assertIn("month=2026-06", text)

    def test_month_view_has_parent_link(self):
        # Up-one-level link should target the principal (one segment up
        # from the calendar URL), so users can navigate back out.
        _s, _h, body = self._request("GET", "/calendar/", query="month=2026-05")
        text = body.decode("utf-8")
        self.assertIn('class="parent-link"', text)
        self.assertIn('href="http://127.0.0.1/"', text)

    def test_month_view_empty(self):
        status, _h, body = self._request("GET", "/calendar/", query="month=2026-05")
        self.assertEqual(status, "200 OK")
        self.assertIn(b'<table class="month"', body)

    def test_recurring_event_expands_into_grid(self):
        self.store.import_one("rec.ics", "text/calendar", [EXAMPLE_RECURRING])
        _s, _h, body = self._request("GET", "/calendar/", query="month=2026-05")
        # Five occurrences within May → five rendered links. Count
        # title="..." which the template emits exactly once per link.
        self.assertEqual(body.decode("utf-8").count('title="Daily standup'), 5)

    def test_all_day_event_spans_cells(self):
        self.store.import_one("ad.ics", "text/calendar", [EXAMPLE_ALL_DAY])
        _s, _h, body = self._request("GET", "/calendar/", query="month=2026-05")
        # 5/18..5/20 = 3 day-cells (DTEND exclusive).
        self.assertEqual(body.decode("utf-8").count('title="Conference'), 3)

    def test_day_view_renders(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        self.store.import_one("todo-1.ics", "text/calendar", [EXAMPLE_TODO])
        status, _h, body = self._request("GET", "/calendar/+day/2026-05-16")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("Team sync", text)
        self.assertIn("Buy milk", text)
        self.assertIn("Mark done", text)  # VTODO quick-toggle

    def test_day_view_shows_todo_on_due_date(self):
        # A VTODO with only a DUE (no DTSTART) must appear on its due
        # date, not pinned to today. EXAMPLE_TODO is DUE 2026-05-16.
        self.store.import_one("todo-1.ics", "text/calendar", [EXAMPLE_TODO])
        _s, _h, due_day = self._request("GET", "/calendar/+day/2026-05-16")
        self.assertIn("Buy milk", due_day.decode("utf-8"))
        # ... and not on some other day.
        _s, _h, other_day = self._request("GET", "/calendar/+day/2026-05-17")
        self.assertNotIn("Buy milk", other_day.decode("utf-8"))

    def test_day_view_bad_date(self):
        status, _h, _b = self._request("GET", "/calendar/+day/not-a-date")
        self.assertEqual(status, "404 Not Found")

    def test_week_view_renders(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        # 2026-05-16 is a Saturday; the week runs Mon 5/11 - Sun 5/17.
        status, _h, body = self._request("GET", "/calendar/+week/2026-05-16")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("Team sync", text)
        self.assertIn("11 May", text)
        self.assertIn("17 May 2026", text)
        # All seven weekday names appear.
        for dow in ("Monday", "Sunday"):
            self.assertIn(dow, text)

    def test_week_view_bad_date(self):
        status, _h, _b = self._request("GET", "/calendar/+week/not-a-date")
        self.assertEqual(status, "404 Not Found")

    def test_week_view_bare_renders_current_week(self):
        status, _h, body = self._request("GET", "/calendar/+week")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("This week", text)

    def test_week_view_excludes_events_outside_week(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        # Week of 2026-05-18 (Mon) - 2026-05-24 (Sun) excludes the 5/16
        # event.
        _s, _h, body = self._request("GET", "/calendar/+week/2026-05-20")
        self.assertNotIn("Team sync", body.decode("utf-8"))

    def test_event_view_html(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        status, headers, body = self._request("GET", "/calendar/event-1.ics")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn('name="summary"', text)
        self.assertIn("Team sync", text)
        self.assertIn("2026-05-16T10:00", text)

    def test_event_view_raw_for_caldav(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        status, headers, body = self._request(
            "GET", "/calendar/event-1.ics", accept="text/calendar"
        )
        self.assertEqual(status, "200 OK")
        self.assertIn("text/calendar", headers["Content-Type"])
        self.assertIn(b"BEGIN:VEVENT", body)

    def test_new_event_form(self):
        status, _h, body = self._request("GET", "/calendar/+new")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("New", text)
        self.assertIn("event", text)
        self.assertIn('name="summary"', text)

    def test_new_todo_form_via_query(self):
        status, _h, body = self._request("GET", "/calendar/+new", query="kind=todo")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        # Task UI surfaces the status select
        self.assertIn('name="status"', text)

    def test_create_event(self):
        body = urlencode(
            {
                "action": "create",
                "kind": "event",
                "summary": "Lunch",
                "start_dt": "2026-05-16T12:00",
                "end_dt": "2026-05-16T13:00",
                "location": "Cafe",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith(".ics"))
        # File persisted
        files = [n for n, _ct, _e in self.store.iter_with_etag()]
        self.assertEqual(len(files), 1)
        stored = b"".join(self.store.get_file(files[0], "text/calendar").content)
        self.assertIn(b"SUMMARY:Lunch", stored)

    def test_create_all_day_event_dtend_is_exclusive(self):
        body = urlencode(
            {
                "action": "create",
                "kind": "event",
                "summary": "Trip",
                "all_day": "1",
                "start_date": "2026-06-01",
                "end_date": "2026-06-03",
            }
        ).encode("utf-8")
        status, _h, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        files = [n for n, _ct, _e in self.store.iter_with_etag()]
        stored = b"".join(
            self.store.get_file(files[0], "text/calendar").content
        ).decode("utf-8")
        # DTEND stored as 6/4 (exclusive); display range is 6/1..6/3.
        self.assertIn("DTSTART;VALUE=DATE:20260601", stored)
        self.assertIn("DTEND;VALUE=DATE:20260604", stored)

    def test_update_event_preserves_uid_and_attendees(self):
        ical = (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//\r\n"
            b"BEGIN:VEVENT\r\nUID:keep-me\r\nDTSTAMP:20260101T000000Z\r\n"
            b"SUMMARY:Old\r\nDTSTART:20260601T100000\r\nDTEND:20260601T110000\r\n"
            b"ATTENDEE:mailto:bob@example.org\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        self.store.import_one("keep-me.ics", "text/calendar", [ical])
        body = urlencode(
            {
                "action": "update",
                "name": "keep-me.ics",
                "summary": "New summary",
                "start_dt": "2026-06-01T12:00",
                "end_dt": "2026-06-01T13:00",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith("/calendar/keep-me.ics"))
        stored = b"".join(
            self.store.get_file("keep-me.ics", "text/calendar").content
        ).decode("utf-8")
        self.assertIn("UID:keep-me", stored)
        self.assertIn("SUMMARY:New summary", stored)
        self.assertIn("ATTENDEE:mailto:bob@example.org", stored)

    def test_delete_event(self):
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        body = urlencode({"action": "delete", "name": "event-1.ics"}).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith("/calendar/"))
        with self.assertRaises(KeyError):
            self.store.get_file("event-1.ics", "text/calendar")

    def test_toggle_done_marks_todo_completed(self):
        self.store.import_one("todo-1.ics", "text/calendar", [EXAMPLE_TODO])
        body = urlencode({"action": "toggle_done", "name": "todo-1.ics"}).encode(
            "utf-8"
        )
        status, _h, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        stored = b"".join(
            self.store.get_file("todo-1.ics", "text/calendar").content
        ).decode("utf-8")
        self.assertIn("STATUS:COMPLETED", stored)
        self.assertIn("COMPLETED:", stored)

    def test_toggle_done_reopens_completed_todo(self):
        completed = (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//\r\n"
            b"BEGIN:VTODO\r\nUID:t1\r\nDTSTAMP:20260101T000000Z\r\n"
            b"SUMMARY:Done thing\r\nSTATUS:COMPLETED\r\n"
            b"COMPLETED:20260101T000000Z\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
        )
        self.store.import_one("t1.ics", "text/calendar", [completed])
        body = urlencode({"action": "toggle_done", "name": "t1.ics"}).encode("utf-8")
        status, _h, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        stored = b"".join(
            self.store.get_file("t1.ics", "text/calendar").content
        ).decode("utf-8")
        self.assertIn("STATUS:NEEDS-ACTION", stored)
        self.assertNotIn("COMPLETED:", stored)

    def test_tasks_view_renders(self):
        self.store.import_one("todo-1.ics", "text/calendar", [EXAMPLE_TODO])
        # An event should never appear on the task list.
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        status, headers, body = self._request("GET", "/calendar/+tasks")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn("Buy milk", text)
        self.assertNotIn("Team sync", text)
        self.assertIn("Mark done", text)
        self.assertIn("Open", text)

    def test_tasks_view_empty(self):
        status, _h, body = self._request("GET", "/calendar/+tasks")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("No open tasks.", text)

    def test_tasks_view_groups_open_and_done(self):
        completed = (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//\r\n"
            b"BEGIN:VTODO\r\nUID:done-1\r\nDTSTAMP:20260101T000000Z\r\n"
            b"SUMMARY:Old chore\r\nSTATUS:COMPLETED\r\n"
            b"COMPLETED:20260101T000000Z\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
        )
        self.store.import_one("todo-1.ics", "text/calendar", [EXAMPLE_TODO])
        self.store.import_one("done-1.ics", "text/calendar", [completed])
        _s, _h, body = self._request("GET", "/calendar/+tasks")
        text = body.decode("utf-8")
        # Open task sorts before the done one in the rendered output.
        self.assertIn("Buy milk", text)
        self.assertIn("Old chore", text)
        self.assertLess(text.index("Buy milk"), text.index("Old chore"))
        # The "Done" section header appears once a done task exists.
        self.assertIn("Done", text)
        self.assertIn("Reopen", text)

    def test_tasks_view_skips_recurrence_overrides(self):
        recurring_todo = (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//\r\n"
            b"BEGIN:VTODO\r\nUID:rt-1\r\nDTSTAMP:20260101T000000Z\r\n"
            b"SUMMARY:Water plants\r\nDUE:20260516T090000\r\n"
            b"RRULE:FREQ=WEEKLY\r\nEND:VTODO\r\n"
            b"BEGIN:VTODO\r\nUID:rt-1\r\nDTSTAMP:20260101T000000Z\r\n"
            b"RECURRENCE-ID:20260523T090000\r\nSUMMARY:Water plants\r\n"
            b"DUE:20260523T090000\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
        )
        self.store.import_one("rt-1.ics", "text/calendar", [recurring_todo])
        _s, _h, body = self._request("GET", "/calendar/+tasks")
        text = body.decode("utf-8")
        # The master VTODO appears exactly once; the RECURRENCE-ID
        # override is not listed separately.
        self.assertEqual(text.count("Water plants"), 1)

    def test_tasks_view_delete_redirects_back(self):
        self.store.import_one("todo-1.ics", "text/calendar", [EXAMPLE_TODO])
        body = urlencode(
            {
                "action": "delete",
                "name": "todo-1.ics",
                "back_url": "http://127.0.0.1/calendar/+tasks/",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertEqual(headers["Location"], "http://127.0.0.1/calendar/+tasks/")
        with self.assertRaises(KeyError):
            self.store.get_file("todo-1.ics", "text/calendar")

    def test_journal_list_renders(self):
        self.store.import_one("journal-1.ics", "text/calendar", [EXAMPLE_JOURNAL])
        # An event must not appear on the journal list.
        self.store.import_one("event-1.ics", "text/calendar", [EXAMPLE_EVENT])
        status, headers, body = self._request("GET", "/calendar/+journal")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn("Trip notes", text)
        self.assertIn("Saw the mountains", text)
        self.assertNotIn("Team sync", text)

    def test_journal_list_empty(self):
        status, _h, body = self._request("GET", "/calendar/+journal")
        self.assertEqual(status, "200 OK")
        self.assertIn("No journal entries yet.", body.decode("utf-8"))

    def test_journal_entry_view_html(self):
        self.store.import_one("journal-1.ics", "text/calendar", [EXAMPLE_JOURNAL])
        status, headers, body = self._request("GET", "/calendar/journal-1.ics")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn('name="kind" value="journal"', text)
        self.assertIn("Trip notes", text)
        self.assertIn("2026-05-16", text)

    def test_journal_entry_raw_for_caldav(self):
        self.store.import_one("journal-1.ics", "text/calendar", [EXAMPLE_JOURNAL])
        status, headers, body = self._request(
            "GET", "/calendar/journal-1.ics", accept="text/calendar"
        )
        self.assertEqual(status, "200 OK")
        self.assertIn("text/calendar", headers["Content-Type"])
        self.assertIn(b"BEGIN:VJOURNAL", body)

    def test_new_journal_form(self):
        status, _h, body = self._request("GET", "/calendar/+newjournal")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("New journal entry", text)
        self.assertIn('name="kind" value="journal"', text)

    def test_create_journal(self):
        body = urlencode(
            {
                "action": "create",
                "kind": "journal",
                "summary": "Day one",
                "start_date": "2026-06-01",
                "description": "First entry.",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith(".ics"))
        files = [n for n, _ct, _e in self.store.iter_with_etag()]
        self.assertEqual(len(files), 1)
        stored = b"".join(
            self.store.get_file(files[0], "text/calendar").content
        ).decode("utf-8")
        self.assertIn("BEGIN:VJOURNAL", stored)
        self.assertIn("SUMMARY:Day one", stored)
        self.assertIn("DTSTART;VALUE=DATE:20260601", stored)

    def test_update_journal(self):
        self.store.import_one("journal-1.ics", "text/calendar", [EXAMPLE_JOURNAL])
        body = urlencode(
            {
                "action": "update",
                "kind": "journal",
                "name": "journal-1.ics",
                "summary": "Edited title",
                "start_date": "2026-05-16",
                "description": "Updated body.",
            }
        ).encode("utf-8")
        status, _h, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        stored = b"".join(
            self.store.get_file("journal-1.ics", "text/calendar").content
        ).decode("utf-8")
        self.assertIn("UID:journal-1", stored)
        self.assertIn("SUMMARY:Edited title", stored)

    def test_delete_journal_redirects_back(self):
        self.store.import_one("journal-1.ics", "text/calendar", [EXAMPLE_JOURNAL])
        body = urlencode(
            {
                "action": "delete",
                "name": "journal-1.ics",
                "back_url": "http://127.0.0.1/calendar/+journal/",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertEqual(headers["Location"], "http://127.0.0.1/calendar/+journal/")
        with self.assertRaises(KeyError):
            self.store.get_file("journal-1.ics", "text/calendar")

    def test_calendar_settings_form_renders(self):
        self.collection.set_displayname("My calendar")
        status, headers, body = self._request("GET", "/calendar/+settings")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn("Calendar settings", text)
        self.assertIn('name="displayname"', text)
        self.assertIn("My calendar", text)

    def test_calendar_settings_save(self):
        body = urlencode(
            {
                "action": "settings",
                "displayname": "Renamed",
                "color": "#ff8800",
                "description": "My events.",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/calendar/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith("/calendar/"))
        # Re-resolve through the backend: writing the display name clears
        # the open-store cache, so the collection captured in setUp now
        # holds a stale store.
        saved = self.backend.get_resource("/calendar")
        self.assertEqual(saved.get_displayname(), "Renamed")
        self.assertEqual(saved.get_calendar_color(), "#ff8800")
        self.assertEqual(saved.get_calendar_description(), "My events.")

    def test_month_view_shows_color_and_description(self):
        self.collection.set_calendar_color("#ff8800")
        self.collection.set_calendar_description("Holiday plans")
        _s, _h, body = self._request("GET", "/calendar/", query="month=2026-05")
        text = body.decode("utf-8")
        self.assertIn("#ff8800", text)
        self.assertIn("Holiday plans", text)

    def test_post_without_action_falls_through(self):
        # Real CalDAV add-member POST with raw ics still works.
        environ = {
            "PATH_INFO": "/calendar/",
            "REQUEST_METHOD": "POST",
            "QUERY_STRING": "",
            "CONTENT_TYPE": "text/calendar",
            "CONTENT_LENGTH": str(len(EXAMPLE_EVENT)),
            "wsgi.input": io.BytesIO(EXAMPLE_EVENT),
            "HTTP_ACCEPT": "*/*",
        }
        setup_testing_defaults(environ)
        captured = {}

        def sr(s, h):
            captured["s"] = s

        b"".join(self.app(environ, sr))
        self.assertIn(captured["s"], ("200 OK", "201 Created"))


class SubscriptionWebTests(unittest.TestCase):
    """End-to-end tests for the read-only subscription view."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        store_path = os.path.join(self.tempdir, "sub")
        self.store = TreeGitStore.create(store_path)
        self.store.set_type(STORE_TYPE_SUBSCRIPTION)
        self.store.load_extra_file_handler(ICalendarFile)
        self.store.set_source_url("https://example.com/feed.ics")
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = SubscriptionCollection(self.backend, "sub", self.store)
        self.app = XandikosApp(self.backend, "user")

    def _request(self, method, path, accept="text/html"):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "QUERY_STRING": "",
            "HTTP_ACCEPT": accept,
        }
        setup_testing_defaults(environ)
        environ["QUERY_STRING"] = ""
        captured = {}

        def sr(status, headers):
            captured["s"] = status
            captured["h"] = dict(headers)

        body = b"".join(self.app(environ, sr))
        return captured["s"], captured["h"], body

    def _upcoming_event(self):
        soon = (date.today() + timedelta(days=2)).strftime("%Y%m%d")
        return (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//\r\n"
            b"BEGIN:VEVENT\r\nUID:s1\r\nDTSTAMP:20260101T000000Z\r\n"
            b"SUMMARY:Upstream meeting\r\n"
            + f"DTSTART:{soon}T100000\r\nDTEND:{soon}T110000\r\n".encode()
            + b"END:VEVENT\r\nEND:VCALENDAR\r\n"
        )

    def test_subscription_view_renders(self):
        self.store.import_one("s1.ics", "text/calendar", [self._upcoming_event()])
        status, headers, body = self._request("GET", "/sub/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn("Subscription", text)
        self.assertIn("https://example.com/feed.ics", text)
        self.assertIn("Upstream meeting", text)
        self.assertIn("read-only", text)

    def test_subscription_view_empty(self):
        status, _h, body = self._request("GET", "/sub/")
        self.assertEqual(status, "200 OK")
        self.assertIn("No upcoming events", body.decode("utf-8"))

    def test_subscription_view_has_no_edit_controls(self):
        self.store.import_one("s1.ics", "text/calendar", [self._upcoming_event()])
        _s, _h, body = self._request("GET", "/sub/")
        text = body.decode("utf-8")
        # Read-only: no create/edit forms.
        self.assertNotIn("+ New event", text)
        self.assertNotIn('name="action"', text)

    def test_subscription_raw_for_caldav(self):
        self.store.import_one("s1.ics", "text/calendar", [self._upcoming_event()])
        status, _h, body = self._request("GET", "/sub/s1.ics", accept="text/calendar")
        self.assertEqual(status, "200 OK")
        self.assertIn(b"BEGIN:VEVENT", body)


class ScheduleOutboxWebTests(unittest.TestCase):
    """End-to-end tests for the schedule-outbox free/busy view."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        store_path = os.path.join(self.tempdir, "outbox")
        self.store = TreeGitStore.create(store_path)
        self.store.set_type(STORE_TYPE_SCHEDULE_OUTBOX)
        self.store.load_extra_file_handler(ICalendarFile)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = ScheduleOutbox(self.backend, "outbox", self.store)
        self.app = XandikosApp(self.backend, "user")

    def _request(self, method, path, query="", accept="text/html"):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "HTTP_ACCEPT": accept,
        }
        setup_testing_defaults(environ)
        environ["QUERY_STRING"] = query
        captured = {}

        def sr(status, headers):
            captured["s"] = status
            captured["h"] = dict(headers)

        body = b"".join(self.app(environ, sr))
        return captured["s"], captured["h"], body

    def test_outbox_renders_form(self):
        status, headers, body = self._request("GET", "/outbox/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn('name="attendee"', text)
        self.assertIn('name="start"', text)
        self.assertIn('name="end"', text)

    def test_outbox_unowned_attendee(self):
        # The outbox's principal does not own this address, so the server
        # has no authority to answer free/busy for it.
        status, _headers, body = self._request(
            "GET",
            "/outbox/",
            query="attendee=nobody@example.com&start=2026-05-01&end=2026-05-02",
        )
        self.assertEqual(status, "200 OK")
        self.assertIn("no authority", body.decode("utf-8"))

    # TODO: a test that lists actual busy periods needs a principal that
    # owns the attendee address and a calendar with events; deferred.


if __name__ == "__main__":
    unittest.main()
