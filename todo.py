#!/usr/bin/python

import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dystros import utils

parser = optparse.OptionParser("travel")
collection_set_options = utils.CollectionSetOptionGroup(parser)
parser.add_option_group(collection_set_options)
opts, args = parser.parse_args()

collections = collection_set_options.get()
vtodos = list(collections.iter_vtodo())

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
