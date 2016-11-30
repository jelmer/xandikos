#!/usr/bin/python3

from icalendar.cal import Calendar, FreeBusy
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dystros import utils

parser = optparse.OptionParser("travel")
collection_set_options = utils.CollectionSetOptionGroup(parser)
parser.add_option_group(collection_set_options)
opts, args = parser.parse_args()

collections = utils.CollectionSet.from_options(opts)
vevents = collections.iter_vevents()

out = Calendar()
freebusy = FreeBusy()
for vevent in vevents:
    freebusy['UID'] = vevent['UID']
    freebusy['DTSTART'] = vevent['DTSTART']
    freebusy['DTEND'] = vevent['DTEND']
    out.add_component(freebusy)

print(out.to_ical())
