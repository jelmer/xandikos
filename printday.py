#!/usr/bin/python

import datetime
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import utils

collections = utils.CollectionSet()

parser = optparse.OptionParser("printday DATE")
parser.add_option_group(collections.get_option_group(parser, 'calendar'))
opts, args = parser.parse_args()

if len(args) < 1:
    parser.print_usage()
    sys.exit(1)

def filter_fn(component):
    if component.name != 'VEVENT':
         return False
    return True

day = utils.asdate(datetime.datetime.strptime(args[0], "%Y%m%d"))

vevents = list(utils.gather_ics([os.path.join(opts.basedir, kind) for kind in opts.kind.split(',')], filter_fn))

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
