#!/usr/bin/python

import datetime
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import utils

DEFAULT_PATH = os.path.join(os.getenv("HOME"), ".config/calypso/collections/jelmer")

parser = optparse.OptionParser("travel")
parser.add_option('--kind', type=str, dest="kind", help="Kind.", default='calendar')
parser.add_option('--basedir', type=str, dest="basedir", help="Input directory.", default=DEFAULT_PATH)
parser.add_option('--category', type=str, dest='category', help='Only display this category.')
opts, args = parser.parse_args()

def filter_fn(component):
    if component.name != 'VEVENT':
         return False
    if opts.category and (
        not 'CATEGORIES' in component or
        not opts.category in component['CATEGORIES']):
         return False
    return True

vevents = list(utils.gather_ics([os.path.join(opts.basedir, kind) for kind in opts.kind.split(',')], filter_fn))

vevents.sort(cmp=utils.cmpEvent)

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
