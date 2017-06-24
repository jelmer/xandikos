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

import unittest

from xandikos.icalendar import ICalendarFile

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


class ExtractCalendarUIDTests(unittest.TestCase):

    def test_extract_str(self):
        self.assertEqual(
            'bdc22720-b9e1-42c9-89c2-a85405d8fbff',
            ICalendarFile([EXAMPLE_VCALENDAR1], 'text/calendar').get_uid())

    def test_extract_no_uid(self):
        fi = ICalendarFile([EXAMPLE_VCALENDAR_NO_UID], 'text/calendar')
        self.assertRaises(KeyError, fi.get_uid)
