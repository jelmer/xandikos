#!/usr/bin/python3
# encoding: utf-8
#
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


import optparse
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

from dystros import filters, utils

parser = optparse.OptionParser("travel")
parser.add_option_group(utils.CalendarOptionGroup(parser))
opts, args = parser.parse_args()

urllib.request.install_opener(utils.get_opener(opts.url))

cals = utils.get_all_calendars(opts.url, filter=utils.comp_filter("VCALENDAR", utils.comp_filter("VTODO")))

vtodos = list(filters.extract_vtodos(cals))

vtodos.sort(key=utils.keyTodo)

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
