#!/usr/bin/python3
# encoding: utf-8
#
# Dystros
# Copyright (C) 2016 Jelmer Vernooĳ <jelmer@jelmer.uk>
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


from icalendar.cal import Calendar, FreeBusy
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dystros import filters, utils

parser = optparse.OptionParser("travel")
collection_set_options = utils.CollectionSetOptionGroup(parser)
parser.add_option_group(collection_set_options)
opts, args = parser.parse_args()

collections = utils.CollectionSet.from_options(opts)
vevents = filters.extract_vevents(collections.iter_calendars())

out = Calendar()
freebusy = FreeBusy()
for vevent in vevents:
    freebusy['UID'] = vevent['UID']
    freebusy['DTSTART'] = vevent['DTSTART']
    freebusy['DTEND'] = vevent['DTEND']
    out.add_component(freebusy)

print(out.to_ical())
