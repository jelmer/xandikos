#!/usr/bin/python

from icalendar.cal import Calendar
import optparse
import os

DEFAULT_PATH = os.path.join(os.getenv("HOME"), ".config/calypso/collections/jelmer")

class CollectionSet(object):
    """Set of iCalendar/vCard collections."""

    def get_option_group(self, parser, default_kind='calendar'):
        """Return a optparser OptionGroup.

        :param parser: An OptionParser
        :param default_kind: Default kind
        :return: An OptionGroup
        """
        self._set_kinds(default_kind)
        self._set_inputdir(DEFAULT_PATH)
        group = optparse.OptionGroup(parser, "Path Settings")
        group.add_option('--kind', type=str, dest="kind", help="Kind.", default=default_kind,
                         callback=self._set_kinds)
        group.add_option('--inputdir', type=str, dest="inputdir", help="Input directory.",
                         default=DEFAULT_PATH, callback=self._set_inputdir)
        return group

    def _set_inputdir(self, value):
        self._inputdir = value

    def _set_kinds(self, value):
        self._kinds = value.split(',')

    def iter_icalendars(self):
        return list(gather_icalendars([os.path.join(self._inputdir, kind) for kind in self._kinds]))

    def iter_vevents(self):
        return extract_vevents(self.iter_calendars())



def extract_vevents(calendars):
    for calendar in calendars:
        for component in calendar.subcomponents:
            if component.name == 'VEVENT':
                yield component


def statuschar(evstatus):
    return {'TENTATIVE': '?',
            'CONFIRMED': '.',
            'CANCELLED': '-'}.get(evstatus, '')


def format_month(dt):
    return dt.strftime("%b")


def format_daterange(start, end):
    if end is None:
        return "%d %s-?" % (start.day, format_month(start))
    if start.month == end.month:
        if start.day == end.day:
            return "%d %s" % (start.day, format_month(start))
        return "%d-%d %s" % (start.day, end.day, format_month(start))
    return "%d %s-%d %s" % (start.day, format_month(start), end.day, format_month(end))


def gather_icalendars(dirs):
    """Find all the ics files in a directory, yield components.

    :param dirs: List of directories to browse
    :return: Iterator over components found
    """
    for bp in dirs:
        for n in os.listdir(bp):
            p = os.path.join(bp, n)
            if not p.endswith(".ics"):
                continue

            yield Calendar.from_ical(open(p, 'r').read())


def asdate(dt):
    if getattr(dt, "date", None):
        a_date = dt.date()
    else:
        a_date = dt
    return dt


def cmpEvent(a, b):
    """Compare two events by date.

    :param a: First event
    :param b: Second event
    :return: -1, 0, or 1 depending on whether a < b, a == b or a > b
    """
    a = a['DTSTART'].dt
    b = b['DTSTART'].dt
    if getattr(a, "date", None):
        a_date = a.date()
        a = (a.hour, a.minute)
    else:
        a_date = a
        a = (0, 0)
    if getattr(b, "date", None):
        b_date = b.date()
        b = (b.hour, b.minute)
    else:
        b_date = b
        b = (0, 0)
    c = cmp(a_date, b_date)
    if c != 0:
        return c
    return cmp(a, b)
