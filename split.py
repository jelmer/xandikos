#!/usr/bin/python3
# encoding: utf-8
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



import hashlib
import logging
import optparse
import urllib.request, urllib.parse, urllib.error
import os
from icalendar.cal import Calendar
from icalendar.prop import vUri, vText
import sys

from dystros import utils

def hasChanged(a, b):
    # FIXME(Jelmer)
    return True

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stderr)
ch.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(levelname)s: %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

parser = optparse.OptionParser("split")
parser.add_option_group(utils.CalendarOptionGroup(parser))
parser.add_option("--prefix", dest="prefix", default="unknown", help="Filename prefix")
parser.add_option('--category', dest='category', default=None, help="Category to add.")
parser.add_option('--status', dest='status', type="choice", choices=["", "tentative", "confirmed"], default=None, help="Status to set.")
opts, args = parser.parse_args()

try:
    import_url = args[0]
except IndexError:
    f = sys.stdin.buffer
    import_url = None
else:
    f = urllib.request.urlopen(import_url)

orig = Calendar.from_ical(f.read())

other = []
items = {}
for component in orig.subcomponents:
    try:
        uid = component['UID']
    except KeyError:
        md5 = hashlib.md5()
        md5.update(component.to_ical())
        component['UID'] = uid = md5.hexdigest()
    if component.name in ('VEVENT', 'VTODO'):
        items[uid] = component
    else:
        other.append(component)

seen = 0
changed = 0
added = 0
for (uid, ev) in items.items():
    seen += 1
    try:
        (href, etag, old) = utils.get_vevent_by_uid(opts.url, uid)
    except KeyError:
        if_match = None
        fname = "%s-%s.ics" % (opts.prefix, uid.replace("/", ""))
        old = None
        url = urllib.parse.urljoin(opts.url, fname)
    else:
        if_match = [etag]
        url = urllib.parse.urljoin(opts.url, href)
    out = Calendar()
    if import_url is not None:
        out['X-IMPORTED-FROM-URL'] = vUri(import_url)
    out.update(list(orig.items()))
    for c in other:
        out.add_component(c)
    if opts.category:
        if isinstance(ev.get('categories', ''), vText):
            ev['categories'] = [ev['categories']]
        ev.setdefault('categories', []).append(vText(opts.category))
    if opts.status and not 'status' in ev:
        ev['status'] = opts.status.upper()
    out.add_component(ev)
    write = hasChanged(old, out)
    if write:
        if old is None:
           added += 1
        else:
           changed += 1
        utils.put(url, out.to_ical(), if_match=if_match)

logger.info('Processed %s. Seen %d, updated %d, new %d', opts.prefix,
             seen, changed, added)
