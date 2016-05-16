#!/usr/bin/python

import datetime
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dystros import utils

parser = optparse.OptionParser("printday DATE")
collection_set_options = utils.CollectionSetOptionGroup(parser)
parser.add_option_group(collection_set_options)
opts, args = parser.parse_args()

if len(args) < 1:
    parser.print_usage()
    sys.exit(1)

day = utils.asdate(datetime.datetime.strptime(args[0], "%Y%m%d"))

collections = collection_set_options.get()
vevents = list(collections.iter_vevents())
vevents.sort(cmp=utils.cmpEvent)

for vevent in vevents:
    if not (day == utils.asdate(vevent['DTSTART'].dt) or
       (day >= utils.asdate(vevent['DTSTART'].dt) and
        day <= utils.asdate(vevent['DTEND'].dt))):
        continue
    summary = vevent['SUMMARY']
    location = vevent.get('LOCATION')
    dtstart = vevent['DTSTART'].dt
    if isinstance(dtstart, datetime.datetime):
        sys.stdout.write('%s' % dtstart.strftime('%H:%M'))
        try:
            dtend = vevent['DTEND'].dt
        except KeyError:
            dtend = None
        else:
            sys.stdout.write('-%s' % dtend.strftime('%H:%M'))
        sys.stdout.write(' ')
    else:
        try:
            dtend = vevent['DTEND'].dt
        except KeyError:
            dtend = None
        sys.stdout.write('%s ' % utils.format_daterange(dtstart, dtend))
    sys.stdout.write("%s" % summary)
    if location:
        sys.stdout.write(" @ %s" % location.replace('\n', ' / '))
    sys.stdout.write(utils.statuschar(vevent.get('STATUS')))
    sys.stdout.write("\n")
