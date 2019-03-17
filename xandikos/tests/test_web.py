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
from ..store.vdir import VdirStore
from ..web import (
    XandikosBackend,
    CalendarCollection,
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
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""


class CalendarCollectionTests(unittest.TestCase):

    def setUp(self):
        super(CalendarCollectionTests, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        self.store = VdirStore.create(os.path.join(self.tempdir, 'c'))
        self.store.load_extra_file_handler(ICalendarFile)
        self.backend = XandikosBackend(self.tempdir)

        self.cal = CalendarCollection(self.backend, 'c', self.store)

    def test_description(self):
        self.store.set_description('foo')
        self.assertEqual('foo', self.cal.get_calendar_description())

    def test_color(self):
        self.assertRaises(KeyError, self.cal.get_calendar_color)
        self.cal.set_calendar_color('#aabbcc')
        self.assertEqual('#aabbcc', self.cal.get_calendar_color())

    def test_get_supported_calendar_components(self):
        self.assertEqual(
            ["VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY"],
            self.cal.get_supported_calendar_components())

    def test_calendar_query_vtodos(self):
        def create_fn(cls):
            f = cls(None)
            f.filter_subcomponent('VCALENDAR').filter_subcomponent('VTODO')
            return f
        self.assertEqual([], list(self.cal.calendar_query(create_fn)))
        self.store.import_one('foo.ics', 'text/calendar', [EXAMPLE_VCALENDAR1])
        result = list(self.cal.calendar_query(create_fn))
        self.assertEqual(1, len(result))
        self.assertEqual('foo.ics', result[0][0])
        self.assertIs(self.store, result[0][1].store)
        self.assertEqual('foo.ics', result[0][1].name)
        self.assertEqual('text/calendar', result[0][1].content_type)

    def test_calendar_query_vtodo_by_uid(self):
        def create_fn(cls):
            f = cls(None)
            f.filter_subcomponent(
                'VCALENDAR').filter_subcomponent(
                'VTODO').filter_property(
                'UID').filter_text_match(
                    b'bdc22720-b9e1-42c9-89c2-a85405d8fbff')
            return f
        self.assertEqual([], list(self.cal.calendar_query(create_fn)))
        self.store.import_one('foo.ics', 'text/calendar', [EXAMPLE_VCALENDAR1])
        result = list(self.cal.calendar_query(create_fn))
        self.assertEqual(1, len(result))
        self.assertEqual('foo.ics', result[0][0])
        self.assertIs(self.store, result[0][1].store)
        self.assertEqual('foo.ics', result[0][1].name)
        self.assertEqual('text/calendar', result[0][1].content_type)

    def test_get_supported_calendar_data_types(self):
        self.assertEqual(
            [('text/calendar', '1.0'), ('text/calendar', '2.0')],
            self.cal.get_supported_calendar_data_types())

    def test_get_max_date_time(self):
        self.assertEqual(
            "99991231T235959Z", self.cal.get_max_date_time())

    def test_get_min_date_time(self):
        self.assertEqual(
            "00010101T000000Z", self.cal.get_min_date_time())

    def test_members(self):
        self.assertEqual([], list(self.cal.members()))
        self.store.import_one('foo.ics', 'text/calendar', [EXAMPLE_VCALENDAR1])
        result = list(self.cal.members())
        self.assertEqual(1, len(result))
        self.assertEqual('foo.ics', result[0][0])
        self.assertIs(self.store, result[0][1].store)
        self.assertEqual('foo.ics', result[0][1].name)
        self.assertEqual('text/calendar', result[0][1].content_type)

    def test_get_member(self):
        self.assertRaises(KeyError, self.cal.get_member, 'foo.ics')
        self.store.import_one('foo.ics', 'text/calendar', [EXAMPLE_VCALENDAR1])
        result = self.cal.get_member('foo.ics')
        self.assertIs(self.store, result.store)
        self.assertEqual('foo.ics', result.name)
        self.assertEqual('text/calendar', result.content_type)

    def test_delete_member(self):
        self.assertRaises(KeyError, self.cal.get_member, 'foo.ics')
        self.store.import_one('foo.ics', 'text/calendar', [EXAMPLE_VCALENDAR1])
        self.cal.get_member('foo.ics')
        self.cal.delete_member('foo.ics')
        self.assertRaises(KeyError, self.cal.get_member, 'foo.ics')

    def test_get_schedule_calendar_transparency(self):
        self.assertEqual(
            caldav.TRANSPARENCY_OPAQUE,
            self.cal.get_schedule_calendar_transparency())
