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
        group = optparse.OptionGroup(parser, "Path Settings")
        group.add_option('--kind', type=str, dest="kind", help="Kind.", default=default_kind)
        group.add_option('--inputdir', type=str, dest="inputdir", help="Input directory.",
                         default=DEFAULT_PATH)
        return group


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


def gather_ics(dirs, filter_fn):
    """Find all the ics files in a directory, yield components.

    :param dirs: List of directories to browse
    :param filter_fn: Function to call on components to decide what to return
    :return: Iterator over components found
    """
    for bp in dirs:
        for n in os.listdir(bp):
            p = os.path.join(bp, n)
            if not p.endswith(".ics"):
                continue

            orig = Calendar.from_ical(open(p, 'r').read())

            for component in orig.subcomponents:
                if filter_fn(component):
                    yield component


def asdate(dt):
    if getattr(dt, "date", None):
        a_date = dt.date()
    else:
        a_date = dt
    return dt


def cmpEvent(a, b):
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
