#!/usr/bin/python3
# encoding: utf-8
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


import datetime
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dystros import filters, utils

parser = optparse.OptionParser("travel")
parser.add_option_group(utils.CalendarOptionGroup(parser))
parser.add_option('--category', type=str, dest='category', help='Only display this category.')
opts, args = parser.parse_args()

def filter_fn(component):
    if opts.category and (
        not 'CATEGORIES' in component or
        not opts.category in component['CATEGORIES']):
         return False
    return True

cals = utils.get_all_calendars(opts.url, filter=utils.comp_filter("VCALENDAR", utils.comp_filter("VEVENT")))

vevents = list(filter(filter_fn, filters.extract_vevents(cals)))
vevents.sort(key=utils.keyEvent)

for vevent in vevents:
    summary = vevent['SUMMARY']
    location = vevent.get('LOCATION')
    dtstart = vevent['DTSTART'].dt
    if isinstance(dtstart, datetime.datetime):
        sys.stdout.write('%12s ' % dtstart.strftime('%d %b %H:%M'))
    else:
        try:
            dtend = vevent['DTEND'].dt
        except KeyError:
            dtend = None
        sys.stdout.write('%12s ' % utils.format_daterange(dtstart, dtend))
    sys.stdout.write("%s" % summary)
    if location:
        sys.stdout.write(" @ %s" % location.replace('\n', ' / '))
    sys.stdout.write(utils.statuschar(vevent.get('STATUS')))
    sys.stdout.write("\n")
