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



from dulwich import porcelain
import datetime
import logging
import optparse
import os
import sys
import time
import urllib.parse
import uuid
from icalendar.cal import Calendar, Event
from icalendar.prop import vDate, vDuration, vDatetime, vText, vUri

sys.path.insert(0, os.path.dirname(__file__))

from dystros.store import GitStore
from dystros import utils

parser = optparse.OptionParser("travel")
parser.add_option_group(utils.CalendarOptionGroup(parser))
parser.add_option('--categories', type=str, dest="categories", help="Comma-separated list of categories to set", default="Travel")
opts, args = parser.parse_args()

description = args[0].strip()
if description[-1] == '?':
    description = description[:-1]
    status = 'TENTATIVE'
elif description[0-1] == '.':
    description = description[:-1]
    status = 'CONFIRMED'
elif description[-1] == '-':
    description = description[:-1]
    status = 'CANCELLED'
else:
    status = None
pts = description.rsplit('@', 1)
if len(pts) == 2:
    location = pts[1].strip()
    description = pts[0].strip()
else:
    location = None
try:
    (datestr, description) = description.split(':', 1)
except ValueError:
    logging.error("Missing ':' in %s", description)
    sys.exit(1)

description = description.strip()

if '-' in datestr:
    (fromstr, tostr) = datestr.split('-')
    if tostr.count(' ') == 1:
        tostr += time.strftime(' %Y')
    dtend = datetime.datetime.strptime(tostr, "%d %b %Y")
    if fromstr.count(' ') == 1:
        fromstr += dtend.strftime(' %Y')
    elif fromstr.count(' ') == 0:
        fromstr += dtend.strftime(' %b %Y')
    dtstart = datetime.datetime.strptime(fromstr, "%d %b %Y")
    duration = None
else:
    if datestr.count(' ') == 1:
        datestr += time.strftime(' %Y')
    dtstart = datetime.datetime.strptime(datestr, "%d %b %Y")
    dtend = None
    duration = datetime.timedelta(1)


props = {
    'categories': opts.categories.split(','),
    'dtstart': vDate(dtstart.date()),
    'created': vDatetime(datetime.datetime.now()),
    'class': 'PUBLIC',
    }
if status is not None:
    props['status'] = status
if location is not None:
    props['location'] = vText(location)
if opts.url:
    props['url'] = vUri(opts.url)
if description is not None:
    props['summary'] = vText(description)
if dtend is not None:
    props['dtend'] = vDate(dtend.date())
if duration is not None:
    props['duration'] = vDuration(duration)

uid = str(uuid.uuid1())
props['UID'] = uid
ev = Event(**props)

c = Calendar()
c.add_component(ev)

fname = uid + '.ics'

url = urllib.parse.urljoin(opts.url, fname)

utils.put(url, c.to_ical())

logging.info('Wrote %s', url)
