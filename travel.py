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


import collections
import datetime
import jinja2
import logging
import optparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dystros import filters, utils, store

parser = optparse.OptionParser("travel")
parser.add_option("--format", choices=["text", "html", "now"], default="text", help="Output format")
parser.add_option("--html-template", type=str, help="Name of HTML template to use.", default="travel.html")
parser.add_option("--category", type=str, help="Category to select", default="Travel")
parser.add_option("--obscured-category", type=str, help="Category to show as opaque.", default="Visitors")
parser.add_option("--show-past-cancelled", action="store_true", default=False, help="Show cancelled past events.")
parser.add_option("--tense", choices=["past", "future", "all"], default="all", help="Tense")
opts, args = parser.parse_args()

def iter_vevents(args):
    for arg in args:
        col = store.open_store(arg)
        for ev in filters.extract_vevents([c for (n, s, c) in col.iter_calendars()]):
            yield ev


TravelEvent = collections.namedtuple("TravelEvent", ["summary", "url", "location", "status", "start", "end"])

travelevs = {}

for ev in iter_vevents(args):
    if ev.get('CLASS') not in (None, 'DEFAULT', 'PUBLIC', 'PRIVATE'):
        logging.info('Skipping %s because it is not public (%s)',
            ev['SUMMARY'], ev['CLASS'])
        continue
    if not 'CATEGORIES' in ev:
        logging.info('Skipping %s because it does not have categories.',
            ev['SUMMARY'])
        continue
    try:
        status = ev['STATUS']
    except KeyError:
        status = None
    start = ev['DTSTART'].dt
    try:
        end = ev['DTEND'].dt
    except KeyError:
        try:
            duration = ev['DURATION'].dt
        except KeyError:
            end = None
        else:
            end = start + (duration - datetime.timedelta(0, 1))
    try:
        url = ev['URL']
    except KeyError:
        url = None

    if ev['CATEGORIES'] == opts.category or opts.category in ev['CATEGORIES']:
        if ev.get('CLASS') == 'PRIVATE':
            summary = "Away"
            location = None
        else:
            summary = ev['SUMMARY']
            try:
                location = ev['LOCATION']
            except KeyError:
                location = None
            if location == summary:
                location = None
    elif opts.obscured_category and (ev['CATEGORIES'] == opts.obscured_category or opts.obscured_category in ev['CATEGORIES']):
        location = None
        summary = opts.obscured_category
    else:
        # TODO(jelmer): There must be a cleaner way of doing this..
        logging.info(
            'Skipping %s because it does not have right catoregies (%s)',
            ev['SUMMARY'], ev.get('CATEGORIES'))
        continue
    travelev = TravelEvent(summary=summary, url=url, location=location,
        status=status, start=start, end=end)
    travelevs.setdefault(travelev.start.year, []).append(travelev)


def evsortkey(ev):
    return ev.start.isoformat()


if not opts.show_past_cancelled:
    def isNotPastCancelled(ev):
        if ev.status != "CANCELLED":
            return True
        return isFuture(ev)
    def isFuture(ev):
        if ev.end is not None:
            end = ev.end
            if getattr(end, "date", None):
                end = end.date()
            return end >= datetime.datetime.now().date()
        start = ev.start
        if getattr(start, "date", None):
            start = start.date()
        return start >= datetime.datetime.now().date()
    def isPast(ev):
        if ev.end is not None:
            end = ev.end
            if getattr(end, "date", None):
                end = end.date()
            return end < datetime.datetime.now().date()
        start = ev.start
        if getattr(start, "date", None):
            start = start.date()
        return start < datetime.datetime.now()
    for year in travelevs:
       travelevs[year] = list(filter(isNotPastCancelled, travelevs[year]))
       if opts.tense == "past":
          travelevs[year] = list(filter(isPast, travelevs[year]))
       elif opts.tense == "future":
          travelevs[year] = list(filter(isFuture, travelevs[year]))

def isCurrent(ev):
    import datetime
    now = datetime.datetime.now().date()
    if ev.end is None:
        return False
    start = ev.start
    if getattr(start, "date", None):
        start = start.date()
    end = ev.end
    if getattr(end, "date", None):
        end = end.date()
    return (now >= start and now <= end)

f = sys.stdout

if opts.format == "text":
    for year in sorted(list(travelevs.keys()), reverse=True):
        if not travelevs[year]:
            continue
        f.write("%d\n" % year)
        evs = travelevs[year]
        for ev in sorted(evs, key=evsortkey, reverse=True):
            f.write("* ")
            f.write(utils.format_daterange(ev.start, ev.end))
            f.write(": %s" % ev.summary)
            if ev.location:
                f.write(" @ %s" % ev.location)
            f.write(utils.statuschar(ev.status))
            f.write("\n")
elif opts.format == "html":
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
    template = env.get_template(opts.html_template)
    def status_char(status):
        if status == "TENTATIVE":
            return "?"
        if status == "CONFIRMED":
            return "."
        return ""
    for year in travelevs:
        if not travelevs[year]:
            continue
        assert isinstance(travelevs[year], list)
        travelevs[year].sort(key=evsortkey, reverse=True)
    print(template.render(events=travelevs, format_daterange=utils.format_daterange,
        status_char=status_char, sorted=sorted, iscurrent=isCurrent))
elif opts.format == "now":
    location = set()
    for evlist in list(travelevs.values()):
        for ev in evlist:
            if not isCurrent(ev):
                continue
            if not ev.location:
                logging.warning('travel event %s does not have location', ev.summary)
            location.add(ev.location or ev.summary)
    if not location:
        print("Home")
    else:
        print(location.pop())
