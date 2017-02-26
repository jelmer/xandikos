# encoding: utf-8
#
# Xandikos
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

"""Calendar Index.

See notes/filters.txt
"""

import tdb

KEYS = [
    'comp=VCALENDAR/comp=VEVENT',
    'comp=VCALENDAR/comp=VTODO',
    'comp=VCALENDAR/comp=VEVENT/prop=UID',
    'comp=VCALENDAR/comp=VTODO/prop=UID',
    'comp=VCALENDAR/comp=VJOURNAL/prop=UID',
    'comp=VCALENDAR/comp=VEVENT/prop=DTSTART',
    'comp=VCALENDAR/comp=VEVENT/prop=DTEND',
    'comp=VCALENDAR/comp=VEVENT/prop=DURATION',
]


def get_index_entry(comp, key):
    (first, sep, rest) = key.partition('/')
    if first.startswith('comp='):
        if comp.name != first[5:]:
            return
        if not rest:
            yield None
        elif rest.startswith('comp='):
            for subcomp in comp.subcomponents:
                for value in get_index_entry(subcomp, rest):
                    yield value
        elif rest.startswith('prop='):
            for value in get_index_entry(comp, rest):
                yield value
    elif first.startswith('prop='):
        try:
            yield comp[first[5:]]
        except KeyError:
            pass
    else:
        raise AssertionError('invalid key name %s' % key)


def get_index_entries(calendar, keys):
    for k in KEYS:
        values = list(get_index_entry(calendar, k))
        if values:
            yield (k, values)


class CalendarIndex(object):

    def insert_entry(self, etag, calendar):
        self.db.transaction_start()
        try:
            for (k, vs) in get_index_entries(calendar, KEYS):
                self.db[etag + '/' + k] = '\n'.join(vs)
            self.db['PRESENT/' + etag] = ''
        finally:
            self.db.transaction_commit()

    def get_indexed_calendar(self, etag):
        raise NotImplementedError(self.get_indexed_calendar)


if __name__ == '__main__':
    from icalendar.cal import Calendar
    import sys
    for arg in sys.argv[1:]:
        with open(arg, 'rb') as f:
            cal = Calendar.from_ical(f.read())
            for (k, vs) in get_index_entries(cal, KEYS):
                print("%s -> %r" % (k, vs))
