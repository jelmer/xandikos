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

import logging
import optparse
import os
import sys
import urllib.request
from icalendar.cal import Calendar

sys.path.insert(0, os.path.dirname(__file__))

from dystros import utils
from dystros.store import ExtractUID

parser = optparse.OptionParser("check")
parser.add_option_group(utils.CalendarOptionGroup(parser))
opts, args = parser.parse_args()

urllib.request.install_opener(utils.get_opener(opts.url))

invalid = set()
uids = {}

for href, cal in utils.get_all_calendars(opts.url):
    try:
        uid = ExtractUID(href, cal)
    except KeyError:
        logging.error(
            'File %s does not have a UID set.',
            href)
    else:
        if uid in uids:
            logging.error(
                'UID %s is used by both %s and %s',
                uid, uids[uid], href)
        uids[uid] = href
