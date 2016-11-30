#!/usr/bin/python3
# encoding: utf-8
#
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


import logging
import optparse
from icalendar.cal import Calendar
import sys
import urllib.request, urllib.parse, urllib.error

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stderr)
ch.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(levelname)s: %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

parser = optparse.OptionParser("fix-songkick")
opts, args = parser.parse_args()

url = args[0]
orig = Calendar.from_ical(urllib.request.urlopen(url).read())

TRACKING_PREFIX = "You’re tracking this event.\n\n"
GOING_PREFIX = "You’re going.\n\n"

def fix_vevent(vevent):
    status = None
    if str(vevent['DESCRIPTION']).startswith(TRACKING_PREFIX):
        vevent['DESCRIPTION'] = vevent['DESCRIPTION'][len(TRACKING_PREFIX):]
    if str(vevent['DESCRIPTION']).startswith(GOING_PREFIX):
        vevent['STATUS'] = 'CONFIRMED'
        vevent['DESCRIPTION'] = vevent['DESCRIPTION'][len(GOING_PREFIX):]
    if str(vevent['DESCRIPTION']).startswith(str(vevent['URL'])):
        vevent['DESCRIPTION'] = vevent['DESCRIPTION'][len(str(vevent['URL'])):]
    if not vevent['DESCRIPTION']:
        del vevent['DESCRIPTION']
    lpts = str(vevent['LOCATION']).split(',')
    for i in reversed(list(range(len(lpts)))):
        loc = (' at ' + ','.join(lpts[:i])) + ' (' + vevent['DTSTART'].dt.strftime('%d %b %y') + ')'
        vevent['SUMMARY'] = vevent['SUMMARY'].replace(loc, '')
    return vevent

out = Calendar()
for component in orig.subcomponents:
    if component.name == 'VEVENT':
        component = fix_vevent(component)
    out.add_component(component)

sys.stdout.write(out.to_ical())
