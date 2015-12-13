#!/usr/bin/python
# encoding: utf-8

import logging
import optparse
from icalendar.cal import Calendar
import sys
import urllib

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
orig = Calendar.from_ical(urllib.urlopen(url).read())

TRACKING_PREFIX = u"You’re tracking this event.\n\n"
GOING_PREFIX = u"You’re going.\n\n"

def fix_vevent(vevent):
    status = None
    if unicode(vevent['DESCRIPTION']).startswith(TRACKING_PREFIX):
        vevent['DESCRIPTION'] = vevent['DESCRIPTION'][len(TRACKING_PREFIX):]
    if unicode(vevent['DESCRIPTION']).startswith(GOING_PREFIX):
        vevent['STATUS'] = 'CONFIRMED'
        vevent['DESCRIPTION'] = vevent['DESCRIPTION'][len(GOING_PREFIX):]
    if unicode(vevent['DESCRIPTION']).startswith(unicode(vevent['URL'])):
        vevent['DESCRIPTION'] = vevent['DESCRIPTION'][len(unicode(vevent['URL'])):]
    if not vevent['DESCRIPTION']:
        del vevent['DESCRIPTION']
    lpts = unicode(vevent['LOCATION']).split(',')
    for i in reversed(range(len(lpts))):
        loc = (' at ' + ','.join(lpts[:i])) + ' (' + vevent['DTSTART'].dt.strftime('%d %b %y') + ')'
        vevent['SUMMARY'] = vevent['SUMMARY'].replace(loc, '')
    return vevent

out = Calendar()
for component in orig.subcomponents:
    if component.name == 'VEVENT':
        component = fix_vevent(component)
    out.add_component(component)

sys.stdout.write(out.to_ical())
