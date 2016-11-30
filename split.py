#!/usr/bin/python3
#
# Dystros
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
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



from dulwich import porcelain
import hashlib
import logging
import optparse
import urllib.request, urllib.parse, urllib.error
import os
from icalendar.cal import Calendar
from icalendar.prop import vUri, vText
import sys

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
parser.add_option("--prefix", dest="prefix", default="unknown", help="Filename prefix")
parser.add_option("--outdir", dest="outdir", default=".", help="Output directory path")
parser.add_option('--category', dest='category', default=None, help="Category to add.")
parser.add_option('--status', dest='status', type="choice", choices=["", "tentative", "confirmed"], default=None, help="Status to set.")
opts, args = parser.parse_args()

url = args[0]
orig = Calendar.from_ical(urllib.request.urlopen(url).read())

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

changed = 0
added = 0
seen = 0

for (uid, ev) in items.items():
    seen += 1
    fname = "%s-%s.ics" % (opts.prefix, uid.replace("/", ""))
    path = os.path.join(opts.outdir, fname)
    out = Calendar()
    out['X-IMPORTED-FROM-URL'] = vUri(url)
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
    try:
        old = Calendar.from_ical(open(path, 'rb').read())
    except IOError:
        old = None
        write = True
    else:
        write = hasChanged(old, out)
    if write:
        if not os.path.exists(path):
           added += 1
        else:
           changed += 1
        with open(path, 'wb') as f:
            f.write(out.to_ical())
        porcelain.add(opts.outdir, [str(fname)])

if changed or added:
    porcelain.commit(opts.outdir, 'Processing %s. Updated: %d, new: %d.' %
                     (opts.prefix, changed, added))

logger.info('Processed %s. Seen %d, updated %d, new %d', opts.prefix,
             seen, changed, added)
