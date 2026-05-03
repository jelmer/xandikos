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

"""Tests for xandikos.itip (RFC 5546 iTIP message construction)."""

import hashlib
import unittest

from icalendar.cal import Calendar

from xandikos import itip


class ExtractSchedulingSignatureTests(unittest.TestCase):
    """Tests for extract_scheduling_signature (RFC 6638 §3.2.10)."""

    BASE_EVENT = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:event-1@example.com
DTSTAMP:20260101T120000Z
LAST-MODIFIED:20260101T120000Z
SEQUENCE:0
DTSTART:20260601T100000Z
DTEND:20260601T110000Z
SUMMARY:Project sync
ORGANIZER:mailto:alice@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:alice@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com
DESCRIPTION:original notes
END:VEVENT
END:VCALENDAR
"""

    def _sig(self, body):
        return itip.extract_scheduling_signature(Calendar.from_ical(body))

    def test_stable_across_dtstamp_changes(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(self.BASE_EVENT.replace(b"20260101T120000Z", b"20260102T130000Z"))
        self.assertEqual(a, b)

    def test_changes_when_description_changes(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(self.BASE_EVENT.replace(b"original notes", b"updated notes"))
        self.assertNotEqual(a, b)

    def test_changes_when_attendee_added(self):
        a = self._sig(self.BASE_EVENT)
        body = (
            self.BASE_EVENT.decode()
            .replace(
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n",
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n"
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:carol@example.com\n",
            )
            .encode()
        )
        self.assertNotEqual(a, self._sig(body))

    def test_changes_when_dtstart_changes(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(
            self.BASE_EVENT.replace(
                b"DTSTART:20260601T100000Z", b"DTSTART:20260601T110000Z"
            )
        )
        self.assertNotEqual(a, b)

    def test_changes_when_sequence_bumps(self):
        a = self._sig(self.BASE_EVENT)
        b = self._sig(self.BASE_EVENT.replace(b"SEQUENCE:0", b"SEQUENCE:1"))
        self.assertNotEqual(a, b)

    def test_attendee_order_independent(self):
        reordered = (
            self.BASE_EVENT.decode()
            .replace(
                "ATTENDEE;PARTSTAT=ACCEPTED:mailto:alice@example.com\n"
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n",
                "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com\n"
                "ATTENDEE;PARTSTAT=ACCEPTED:mailto:alice@example.com\n",
            )
            .encode()
        )
        self.assertEqual(self._sig(self.BASE_EVENT), self._sig(reordered))

    def test_partstat_change_changes_signature(self):
        replied = self.BASE_EVENT.replace(
            b"ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com",
            b"ATTENDEE;PARTSTAT=ACCEPTED:mailto:bob@example.com",
        )
        self.assertNotEqual(self._sig(self.BASE_EVENT), self._sig(replied))

    def test_only_vtimezone_yields_empty_digest(self):
        body = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VTIMEZONE
TZID:UTC
END:VTIMEZONE
END:VCALENDAR
"""
        self.assertEqual(self._sig(body), hashlib.sha256().digest())

    def test_recurrence_id_distinguishes_overrides(self):
        body_with_override = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:rec@example.com
DTSTAMP:20260101T120000Z
DTSTART:20260601T100000Z
SUMMARY:Series
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
BEGIN:VEVENT
UID:rec@example.com
DTSTAMP:20260101T120000Z
RECURRENCE-ID:20260602T100000Z
DTSTART:20260602T120000Z
SUMMARY:Series (override)
END:VEVENT
END:VCALENDAR
"""
        body_without_override = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:rec@example.com
DTSTAMP:20260101T120000Z
DTSTART:20260601T100000Z
SUMMARY:Series
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR
"""
        self.assertNotEqual(
            self._sig(body_with_override), self._sig(body_without_override)
        )


CANCEL_SOURCE = b"""\
BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Test//EN\r
BEGIN:VEVENT\r
UID:meeting@example.com\r
DTSTAMP:20260101T000000Z\r
DTSTART:20260601T100000Z\r
DTEND:20260601T110000Z\r
SUMMARY:Sync\r
SEQUENCE:2\r
ORGANIZER:mailto:alice@example.com\r
ATTENDEE:mailto:bob@example.com\r
END:VEVENT\r
END:VCALENDAR\r
"""


class BuildItipCancelTests(unittest.TestCase):
    """Tests for build_itip_cancel (RFC 5546 §3.2.5)."""

    def _build(self):
        cal = Calendar.from_ical(CANCEL_SOURCE.decode("utf-8"))
        return itip.build_itip_cancel(cal)

    def test_method_is_cancel(self):
        self.assertEqual("CANCEL", str(self._build()["METHOD"]))

    def test_sequence_bumped(self):
        out = self._build()
        ev = next(c for c in out.subcomponents if c.name == "VEVENT")
        self.assertEqual(3, int(ev["SEQUENCE"]))

    def test_status_cancelled(self):
        out = self._build()
        ev = next(c for c in out.subcomponents if c.name == "VEVENT")
        self.assertEqual("CANCELLED", str(ev["STATUS"]))

    def test_uid_preserved(self):
        out = self._build()
        ev = next(c for c in out.subcomponents if c.name == "VEVENT")
        self.assertEqual("meeting@example.com", str(ev["UID"]))

    def test_attendees_preserved(self):
        out = self._build()
        ev = next(c for c in out.subcomponents if c.name == "VEVENT")
        attendees = ev.get("ATTENDEE")
        if not isinstance(attendees, list):
            attendees = [attendees]
        self.assertIn("mailto:bob@example.com", [str(a) for a in attendees])

    def test_dtstamp_refreshed(self):
        out = self._build()
        ev = next(c for c in out.subcomponents if c.name == "VEVENT")
        # The new DTSTAMP should not be the old one.
        self.assertNotEqual("20260101T000000Z", ev["DTSTAMP"].to_ical().decode())

    def test_zero_sequence_default(self):
        body = CANCEL_SOURCE.replace(b"SEQUENCE:2\r\n", b"")
        out = itip.build_itip_cancel(Calendar.from_ical(body.decode("utf-8")))
        ev = next(c for c in out.subcomponents if c.name == "VEVENT")
        self.assertEqual(1, int(ev["SEQUENCE"]))

    def test_vtimezone_passed_through_unchanged(self):
        body = b"""\
BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Test//EN\r
BEGIN:VTIMEZONE\r
TZID:UTC\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
UID:e1\r
DTSTAMP:20260101T000000Z\r
DTSTART:20260601T100000Z\r
ORGANIZER:mailto:a@x\r
ATTENDEE:mailto:b@x\r
END:VEVENT\r
END:VCALENDAR\r
"""
        out = itip.build_itip_cancel(Calendar.from_ical(body.decode("utf-8")))
        tz = next(c for c in out.subcomponents if c.name == "VTIMEZONE")
        # No SEQUENCE/STATUS injected on a non-scheduling component.
        self.assertNotIn("SEQUENCE", tz)
        self.assertNotIn("STATUS", tz)


if __name__ == "__main__":
    unittest.main()
