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

from datetime import datetime

import unittest

from icalendar.cal import Event

from xandikos import (
    collation as _mod_collation,
)
from xandikos.icalendar import (
    CalendarFilter,
    ICalendarFile,
    MissingProperty,
    TextMatcher,
    validate_calendar,
    apply_time_range_vevent,
    as_tz_aware_ts,
)
from xandikos.store import InvalidFileContents

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
        fi = ICalendarFile([EXAMPLE_VCALENDAR1], 'text/calendar')
        self.assertEqual(
            'bdc22720-b9e1-42c9-89c2-a85405d8fbff',
            fi.get_uid())
        fi.validate()

    def test_extract_no_uid(self):
        fi = ICalendarFile([EXAMPLE_VCALENDAR_NO_UID], 'text/calendar')
        fi.validate()
        self.assertEqual(["Missing required field UID"],
                         list(validate_calendar(fi.calendar, strict=True)))
        self.assertEqual([],
                         list(validate_calendar(fi.calendar, strict=False)))
        self.assertRaises(KeyError, fi.get_uid)

    def test_invalid_character(self):
        fi = ICalendarFile([EXAMPLE_VCALENDAR_INVALID_CHAR], 'text/calendar')
        self.assertRaises(InvalidFileContents, fi.validate)
        self.assertEqual(["Invalid character b'\\\\x0c' in field SUMMARY"],
                         list(validate_calendar(fi.calendar, strict=False)))


class CalendarFilterTests(unittest.TestCase):

    def setUp(self):
        self.cal = ICalendarFile([EXAMPLE_VCALENDAR1], 'text/calendar')

    def test_simple_comp_filter(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent('VCALENDAR').filter_subcomponent('VEVENT')
        self.assertEqual(filter.indexes(), [['C=VCALENDAR/C=VEVENT']])
        self.assertEqual(
            self.cal.get_indexes(
                ['C=VCALENDAR/C=VEVENT', 'C=VCALENDAR/C=VTODO']),
            {'C=VCALENDAR/C=VEVENT': [], 'C=VCALENDAR/C=VTODO': [True]})
        self.assertFalse(
            filter.check_from_indexes(
                'file', {'C=VCALENDAR/C=VEVENT': [],
                         'C=VCALENDAR/C=VTODO': [True]}))
        self.assertFalse(filter.check('file', self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent('VCALENDAR').filter_subcomponent('VTODO')
        self.assertTrue(filter.check('file', self.cal))
        self.assertTrue(
            filter.check_from_indexes(
                'file', {'C=VCALENDAR/C=VEVENT': [],
                         'C=VCALENDAR/C=VTODO': [True]}))

    def test_prop_presence_filter(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent('VCALENDAR').filter_subcomponent(
            'VTODO').filter_property('X-SUMMARY')
        self.assertEqual(
            filter.indexes(),
            [['C=VCALENDAR/C=VTODO/P=X-SUMMARY']])
        self.assertFalse(
            filter.check_from_indexes(
                'file', {'C=VCALENDAR/C=VTODO/P=X-SUMMARY': []}))
        self.assertFalse(filter.check('file', self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent('VCALENDAR').filter_subcomponent(
            'VTODO').filter_property('SUMMARY')
        self.assertTrue(
            filter.check_from_indexes(
                'file', {'C=VCALENDAR/C=VTODO/P=SUMMARY': [b'do something']}))
        self.assertTrue(filter.check('file', self.cal))

    def test_prop_text_match(self):
        filter = CalendarFilter(None)
        filter.filter_subcomponent('VCALENDAR').filter_subcomponent(
            'VTODO').filter_property('SUMMARY').filter_text_match(
                b'do something different')
        self.assertEqual(
            filter.indexes(),
            [['C=VCALENDAR/C=VTODO/P=SUMMARY']])
        self.assertFalse(
            filter.check_from_indexes(
                'file', {'C=VCALENDAR/C=VTODO/P=SUMMARY': [b'do something']}))
        self.assertFalse(filter.check('file', self.cal))
        filter = CalendarFilter(None)
        filter.filter_subcomponent('VCALENDAR').filter_subcomponent(
            'VTODO').filter_property('SUMMARY').filter_text_match(
                b'do something')
        self.assertTrue(
            filter.check_from_indexes(
                'file', {'C=VCALENDAR/C=VTODO/P=SUMMARY': [b'do something']}))
        self.assertTrue(filter.check('file', self.cal))


class TextMatchTest(unittest.TestCase):

    def test_default_collation(self):
        tm = TextMatcher(b"foobar")
        self.assertTrue(tm.match(b"FOOBAR"))
        self.assertTrue(tm.match(b"foobar"))
        self.assertFalse(tm.match(b"fobar"))

    def test_casecmp_collation(self):
        tm = TextMatcher(b'foobar', collation='i;ascii-casemap')
        self.assertTrue(tm.match(b"FOOBAR"))
        self.assertTrue(tm.match(b"foobar"))
        self.assertFalse(tm.match(b"fobar"))

    def test_cmp_collation(self):
        tm = TextMatcher(b'foobar', 'i;octet')
        self.assertFalse(tm.match(b"FOOBAR"))
        self.assertTrue(tm.match(b"foobar"))
        self.assertFalse(tm.match(b"fobar"))

    def test_unknown_collation(self):
        self.assertRaises(
            _mod_collation.UnknownCollation, TextMatcher,
            b'foobar', collation='i;blah')


class ApplyTimeRangeVeventTests(unittest.TestCase):

    def _tzify(self, dt):
        return as_tz_aware_ts(dt, 'UTC')

    def test_missing_dtstart(self):
        ev = Event()
        self.assertRaises(
            MissingProperty, apply_time_range_vevent,
            datetime.utcnow(), datetime.utcnow(), ev, self._tzify)
