#!/usr/bin/python

from dulwich import porcelain
import datetime
import hashlib
import logging
import optparse
import os
import sys
import time
from icalendar.cal import Calendar, Event
from icalendar.prop import vDate, vDuration, vDatetime, vText, vUri

sys.path.insert(0, os.path.dirname(__file__))

import utils

DEFAULT_OUTPUT_DIR = os.path.join(utils.DEFAULT_PATH, "travel")

parser = optparse.OptionParser("travel")
parser.add_option('--url', type=str, dest="url", help="Associated URL.", default=None)
parser.add_option('--categories', type=str, dest="categories", help="Comma-separated list of categories to set", default="Travel")
parser.add_option('--outputdir', type=str, dest="outputdir", help="Output directory.",
                  default=DEFAULT_OUTPUT_DIR)
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

ev = Event(**props)

c = Calendar()
c.add_component(ev)

md5 = hashlib.md5()
md5.update(c.to_ical())

uid = md5.hexdigest()

props['UID'] = uid

fname = uid + '.ics'
path = os.path.join(opts.outputdir, fname)
porcelain.add(opts.outputdir, path)
porcelain.commit(opts.outputdir, 'Add %s.' % description)

with open(path, 'w') as f:
    f.write(c.to_ical())

logging.info('Wrote %s', path)
