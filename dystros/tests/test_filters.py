# Dystros
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
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

from icalendar.cal import Calendar
from dystros import filters

import unittest

EXAMPLE_VEVENT1 = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VEVENT
CREATED:20150314T223512Z
DTSTAMP:20150527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VEVENT
END:VCALENDAR
"""

EXAMPLE_VTODO1 = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20120314T223512Z
DTSTAMP:20130527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something else
UID:bdc22764-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""


class FilterTests(unittest.TestCase):

    def test_extract_vevents(self):
        event1 = Calendar.from_ical(EXAMPLE_VEVENT1)
        todo1 = Calendar.from_ical(EXAMPLE_VTODO1)
        self.assertEqual([event1.subcomponents[0]], list(filters.extract_vevents([event1, todo1])))

    def test_extract_vtodo(self):
        event1 = Calendar.from_ical(EXAMPLE_VEVENT1)
        todo1 = Calendar.from_ical(EXAMPLE_VTODO1)
        self.assertEqual([todo1.subcomponents[0]], list(filters.extract_vtodos([event1, todo1])))

