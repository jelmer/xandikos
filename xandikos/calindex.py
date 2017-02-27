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

import os
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
            yield b''
        elif rest.startswith('comp='):
            for subcomp in comp.subcomponents:
                for value in get_index_entry(subcomp, rest):
                    yield value
        elif rest.startswith('prop='):
            for value in get_index_entry(comp, rest):
                yield value
    elif first.startswith('prop='):
        try:
            v = comp[first[5:]]
        except KeyError:
            pass
        else:
            yield v.to_ical()
    else:
        raise AssertionError('invalid key name %s' % key)


def get_index_entries(calendar, keys):
    for k in KEYS:
        values = list(get_index_entry(calendar, k))
        if values:
            yield (k, values)


class CalendarIndex(object):

    def __init__(self, path):
        self.db = tdb.open(path, flags=os.O_RDWR|os.O_CREAT, tdb_flags=tdb.DEFAULT)

    @classmethod
    def open_from_store(cls, store):
        return cls(os.path.join(store.repo.controldir(), 'calindex.tdb'))

    def insert_entry(self, etag, calendar):
        self.db.transaction_start()
        try:
            for (k, vs) in get_index_entries(calendar, KEYS):
                self.db[b'KEY/' + etag.encode('ascii') + b'/' + k.encode('utf-8')] = b'\n'.join(vs)
            self.db[b'PRESENT/' + etag.encode('ascii')] = b''
        finally:
            self.db.transaction_commit()

    def __contains__(self):
        return (b'PRESENT/' + etag.encode('ascii') in self.db)

    def get_indexed_calendar(self, etag):
        if not etag in self:
            raise KeyError(etag)
        return IndexedCalendar(etag)


if __name__ == '__main__':
    from xandikos.store import open_store
    from icalendar.cal import Calendar
    import sys
    store = open_store(sys.argv[1])
    index = CalendarIndex.open_from_store(store)
    for (name, content_type, etag) in store.iter_with_etag():
        if content_type != 'text/calendar':
            continue
        fi = store.get_file(name, content_type, etag)
        index.insert_entry(etag, fi.calendar)
