#!/usr/bin/python

import optparse
import os
import sys
from icalendar.cal import Calendar

sys.path.insert(0, os.path.dirname(__file__))

import utils

collections = utils.CollectionSet()

parser = optparse.OptionParser("travel")
parser.add_option_group(collections.get_option_group(parser))
opts, args = parser.parse_args()

vtodos = []

for kind in opts.kind.split(','):
    bp = os.path.join(opts.inputdir, kind)
    for n in os.listdir(bp):
        p = os.path.join(bp, n)
        if not p.endswith(".ics"):
            continue

        orig = Calendar.from_ical(open(p, 'r').read())

        for component in orig.subcomponents:
            if component.name == 'VTODO':
                vtodos.append(component)

def todoKey(vtodo):
    return (vtodo.get('PRIORITY'), vtodo.get('DUE'), vtodo['SUMMARY'])

vtodos.sort(key=todoKey)

for vtodo in vtodos:
    status = str(vtodo.get('STATUS', 'NEEDS-ACTION'))
    if status in ('COMPLETED', 'CANCELLED'):
        continue
    summary = vtodo['SUMMARY']
    location = vtodo.get('LOCATION')
    priority = vtodo.get('PRIORITY')
    if priority is not None:
        sys.stdout.write("(%d) " % priority)
    sys.stdout.write("%s" % summary)
    if location:
        sys.stdout.write(" @ %s" % location)
    if 'DUE' in vtodo:
        sys.stdout.write(" (due %s)" % vtodo['DUE'].dt.strftime("%Y %b %d"))
    sys.stdout.write("\n")
