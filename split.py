#!/usr/bin/python

from dulwich import porcelain
import logging
import optparse
import urllib
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
orig = Calendar.from_ical(urllib.urlopen(url).read())

other = []
evs = {}
for component in orig.subcomponents:
    if component.name == 'VEVENT':
        evs[component['UID']] = component
    else:
        other.append(component)

changed = 0
added = 0
seen = 0

for (uid, ev) in evs.iteritems():
    seen += 1
    fname = "%s-%s.ics" % (opts.prefix, uid.replace("/", ""))
    path = os.path.join(opts.outdir, fname)
    out = Calendar()
    out['X-IMPORTED-FROM-URL'] = vUri(url)
    out.update(orig.items())
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
