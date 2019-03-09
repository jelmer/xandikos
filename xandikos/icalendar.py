# Xandikos
# Copyright (C) 2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 3
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

"""ICalendar file handling.

"""

import datetime
import logging

from icalendar.cal import Calendar, component_factory
from icalendar.prop import vText
from xandikos.store import (
    Filter,
    File,
    InvalidFileContents,
)

from . import (
    collation as _mod_collation,
)

# TODO(jelmer): Populate this further based on
# https://tools.ietf.org/html/rfc5545#3.3.11
_INVALID_CONTROL_CHARACTERS = ['\x0c', '\x01']


class MissingProperty(Exception):

    def __init__(self, property_name):
        super(MissingProperty, self).__init__(
            "Property %r missing" % property_name)
        self.property_name = property_name


def validate_calendar(cal, strict=False):
    """Validate a calendar object.

    :param cal: Calendar object
    :return: iterator over error messages
    """
    for error in validate_component(cal, strict=strict):
        yield error


def validate_component(comp, strict=False):
    """Validate a calendar component.

    :param comp: Calendar component
    """
    # Check text fields for invalid characters
    for (name, value) in comp.items():
        if isinstance(value, vText):
            for c in _INVALID_CONTROL_CHARACTERS:
                if c in value:
                    yield "Invalid character %s in field %s" % (
                        c.encode('unicode_escape'), name)
    if strict:
        for required in comp.required:
            try:
                comp[required]
            except KeyError:
                yield "Missing required field %s" % required
    for subcomp in comp.subcomponents:
        for error in validate_component(subcomp, strict=strict):
            yield error


def calendar_component_delta(old_cal, new_cal):
    """Find the differences between components in two calendars.

    :param old_cal: Old calendar (can be None)
    :param new_cal: New calendar (can be None)
    :yield: (old_component, new_component) tuples (either can be None)
    """
    by_uid = {}
    by_content = {}
    by_idx = {}
    idx = 0
    for component in getattr(old_cal, "subcomponents", []):
        try:
            by_uid[component["UID"]] = component
        except KeyError:
            by_content[component.to_ical()] = True
            by_idx[idx] = component
            idx += 1
    idx = 0
    for component in new_cal.subcomponents:
        try:
            old_component = by_uid.pop(component["UID"])
        except KeyError:
            if not by_content.pop(component.to_ical(), None):
                # Not previously present
                yield (by_idx.get(idx, component_factory[component.name]()),
                       component)
            by_idx.pop(idx, None)
        else:
            yield (old_component, component)
    for old_component in by_idx.values():
        yield (old_component, component_factory[old_component.name]())


def calendar_prop_delta(old_component, new_component):
    fields = set([field for field in old_component or []] +
                 [field for field in new_component or []])
    for field in fields:
        old_value = old_component.get(field)
        new_value = new_component.get(field)
        if (
            getattr(old_value, 'to_ical', None) is None or
            getattr(new_value, 'to_ical', None) is None or
            old_value.to_ical() != new_value.to_ical()
        ):
            yield (field, old_value, new_value)


def describe_component(component):
    if component.name == "VTODO":
        try:
            return "task '%s'" % component["SUMMARY"]
        except KeyError:
            return "task"
    else:
        try:
            return component["SUMMARY"]
        except KeyError:
            return "calendar item"


DELTA_IGNORE_FIELDS = set(["LAST-MODIFIED", "SEQUENCE", "DTSTAMP", "PRODID",
                           "CREATED", "COMPLETED", "X-MOZ-GENERATION",
                           "X-LIC-ERROR", "UID"])


def describe_calendar_delta(old_cal, new_cal):
    """Describe the differences between two calendars.

    :param old_cal: Old calendar (can be None)
    :param new_cal: New calendar (can be None)
    :yield: Lines describing changes
    """
    # TODO(jelmer): Extend
    for old_component, new_component in calendar_component_delta(old_cal,
                                                                 new_cal):
        if not new_component:
            yield "Deleted %s" % describe_component(old_component)
            continue
        description = describe_component(new_component)
        if not old_component:
            yield "Added %s" % describe_component(new_component)
            continue
        for field, old_value, new_value in calendar_prop_delta(old_component,
                                                               new_component):
            if field.upper() in DELTA_IGNORE_FIELDS:
                continue
            if (
                old_component.name.upper() == "VTODO" and
                field.upper() == "STATUS"
            ):
                if new_value is None:
                    yield "status of %s deleted" % description
                else:
                    human_readable = {
                        "NEEDS-ACTION": "needing action",
                        "COMPLETED": "complete",
                        "CANCELLED": "cancelled"}
                    yield "%s marked as %s" % (
                        description,
                        human_readable.get(new_value.upper(), new_value))
            elif field.upper() == 'DESCRIPTION':
                yield "changed description of %s" % description
            elif field.upper() == 'SUMMARY':
                yield "changed summary of %s" % description
            elif field.upper() == 'LOCATION':
                yield "changed location of %s to %s" % (description, new_value)
            elif (old_component.name.upper() == "VTODO" and
                  field.upper() == "PERCENT-COMPLETE" and
                  new_value is not None):
                yield "%s marked as %d%% completed." % (
                    description, new_value)
            elif field.upper() == 'DUE':
                yield "changed due date for %s from %s to %s" % (
                    description, old_value.dt if old_value else 'none',
                    new_value.dt if new_value else 'none')
            elif field.upper() == 'DTSTART':
                yield "changed start date/time of %s from %s to %s" % (
                    description, old_value.dt if old_value else 'none',
                    new_value.dt if new_value else 'none')
            elif field.upper() == 'DTEND':
                yield "changed end date/time of %s from %s to %s" % (
                    description, old_value.dt if old_value else 'none',
                    new_value.dt if new_value else 'none')
            elif field.upper() == 'CLASS':
                yield "changed class of %s from %s to %s" % (
                    description, old_value.lower() if old_value else 'none',
                    new_value.lower() if new_value else 'none')
            else:
                yield "modified field %s in %s" % (field, description)
                logging.debug("Changed %s/%s or %s/%s from %s to %s.",
                              old_component.name, field, new_component.name,
                              field, old_value, new_value)


def apply_time_range_vevent(start, end, comp, tzify):
    if 'DTSTART' not in comp:
        raise MissingProperty('DTSTART')

    if not (end > tzify(comp['DTSTART'].dt)):
        return False

    if 'DTEND' in comp:
        if tzify(comp['DTEND'].dt) < tzify(comp['DTSTART'].dt):
            logging.debug('Invalid DTEND < DTSTART')
        return (start < tzify(comp['DTEND'].dt))

    if 'DURATION' in comp:
        return (start < tzify(comp['DTSTART'].dt) + comp['DURATION'].dt)
    if getattr(comp['DTSTART'].dt, 'time', None) is not None:
        return (start <= tzify(comp['DTSTART'].dt))
    else:
        return (start < (tzify(comp['DTSTART'].dt) + datetime.timedelta(1)))


def apply_time_range_vjournal(start, end, comp, tzify):
    if 'DTSTART' not in comp:
        return False

    if not (end > tzify(comp['DTSTART'].dt)):
        return False

    if getattr(comp['DTSTART'].dt, 'time', None) is not None:
        return (start <= tzify(comp['DTSTART'].dt))
    else:
        return (start < (tzify(comp['DTSTART'].dt) + datetime.timedelta(1)))


def apply_time_range_vtodo(start, end, comp, tzify):
    if 'DTSTART' in comp:
        if 'DURATION' in comp and 'DUE' not in comp:
            return (
                start <= tzify(comp['DTSTART'].dt) + comp['DURATION'].dt and
                (end > tzify(comp['DTSTART'].dt) or
                 end >= tzify(comp['DTSTART'].dt) + comp['DURATION'].dt)
            )
        elif 'DUE' in comp and 'DURATION' not in comp:
            return (
                (start <= tzify(comp['DTSTART'].dt) or
                 start < tzify(comp['DUE'].dt)) and
                (end > tzify(comp['DTSTART'].dt) or
                 end < tzify(comp['DUE'].dt))
            )
        else:
            return (start <= tzify(comp['DTSTART'].dt) and
                    end > tzify(comp['DTSTART'].dt))
    elif 'DUE' in comp:
        return start < tzify(comp['DUE'].dt) and end >= tzify(comp['DUE'].dt)
    elif 'COMPLETED' in comp:
        if 'CREATED' in comp:
            return (
                (start <= tzify(comp['CREATED'].dt) or
                 start <= tzify(comp['COMPLETED'].dt)) and
                (end >= tzify(comp['CREATED'].dt) or
                 end >= tzify(comp['COMPLETED'].dt))
            )
        else:
            return (
                start <= tzify(comp['COMPLETED'].dt) and
                end >= tzify(comp['COMPLETED'].dt)
            )
    elif 'CREATED' in comp:
        return end >= tzify(comp['CREATED'].dt)
    else:
        return True


def apply_time_range_vfreebusy(start, end, comp, tzify):
    if 'DTSTART' in comp and 'DTEND' in comp:
        return (
            start <= tzify(comp['DTEND'].dt) and
            end > tzify(comp['DTEND'].dt)
        )

    for period in comp.get('FREEBUSY', []):
        if start < period.end and end > period.start:
            return True

    return False


def apply_time_range_valarm(start, end, comp, tzify):
    raise NotImplementedError(apply_time_range_valarm)


class ComponentTimeRangeMatcher(object):

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def match(self, comp, tzify):
        # According to https://tools.ietf.org/html/rfc4791, section 9.9 these
        # are the properties to check.
        component_handlers = {
            'VEVENT': apply_time_range_vevent,
            'VTODO': apply_time_range_vtodo,
            'VJOURNAL': apply_time_range_vjournal,
            'VFREEBUSY': apply_time_range_vfreebusy,
            'VALARM': apply_time_range_valarm}
        try:
            component_handler = component_handlers[comp.name]
        except KeyError:
            logging.warning('unknown component %r in time-range filter',
                            comp.name)
            return False
        return component_handler(self.start, self.end, comp, tzify)


class TextMatcher(object):

    def __init__(self, text, collation='i;ascii-casemap',
                 negate_condition=False):
        self.text = text
        self.collation = collation
        self.negate_condition = negate_condition

    def match(self, prop):
        matches = _mod_collation.get_collation(self.collation)(self.text, prop)
        if self.negate_condition:
            return not matches
        else:
            return matches


class ComponentFilter(object):

    def __init__(self, name, children=None, is_not_defined=False,
                 time_range=None):
        self.name = name
        self.children = children
        self.is_not_defined = is_not_defined
        self.time_range = time_range
        self.children = children or []

    def match(self, comp, tzify):
        # From https://tools.ietf.org/html/rfc4791, 9.7.1:
        # A CALDAV:comp-filter is said to match if:

        # 2. The CALDAV:comp-filter XML element contains a
        # CALDAV:is-not-defined XML element and the calendar object or calendar
        # component type specified by the "name" attribute does not exist in
        # the current scope;
        if self.is_not_defined:
            return comp.name != self.name

        # 1: The CALDAV:comp-filter XML element is empty and the calendar
        # object or calendar component type specified by the "name" attribute
        # exists in the current scope;
        if comp.name != self.name:
            return False

        # 3. The CALDAV:comp-filter XML element contains a CALDAV:time-range
        # XML element and at least one recurrence instance in the targeted
        # calendar component is scheduled to overlap the specified time range
        if self.time_range is not None and not self.time_range.match(comp):
            return False

        # ... and all specified CALDAV:prop-filter and CALDAV:comp-filter child
        # XML elements also match the targeted calendar component;
        for child in self.children:
            if isinstance(child, ComponentFilter):
                if not any(child.match(c, tzify) for c in comp.subcomponents):
                    return False
            elif isinstance(child, PropertyFilter):
                if not child.match(comp, tzify):
                    return False
            else:
                raise TypeError(child)

        return True


class PropertyFilter(object):

    def __init__(self, name, children=None, is_not_defined=False):
        self.name = name
        self.is_not_defined = is_not_defined
        self.children = children or []

    def match(self, comp):
        # From https://tools.ietf.org/html/rfc4791, 9.7.2:
        # A CALDAV:comp-filter is said to match if:

        # The CALDAV:prop-filter XML element contains a CALDAV:is-not-defined
        # XML element and no property of the type specified by the "name"
        # attribute exists in the enclosing calendar component;

        if self.is_not_defined:
            return self.name not in comp

        try:
            prop = comp[self.name]
        except KeyError:
            return False

        if self.time_range and not self.time_range.match(prop):
            return False

        for child in self.children:
            if not child.match(prop):
                return False

        return True


class ParameterFilter(object):

    def __init__(self, name, is_not_defined=False):
        self.name = name
        self.is_not_defined = is_not_defined

    def match(self, prop):
        if self.is_not_defined:
            return self.name not in prop.params

        try:
            value = prop.params[self.name]
        except KeyError:
            return False

        for child in self.children:
            if not child.match(value):
                return False
        return True


class CalendarFilter(Filter):
    """A filter that works on ICalendar files."""

    def __init__(self, tzify, component_filter=None):
        self.component_filter = component_filter
        self.tzify = tzify

    def check(self, name, file):
        if file.content_type != 'text/calendar':
            return False
        c = file.calendar
        if c is None:
            return False

        if self.component_filter is None:
            return True

        try:
            return self.component_filter.match(file.calendar, self.tzify)
        except MissingProperty as e:
            logging.warning(
                'calendar_query: Ignoring calendar object %s, due '
                'to missing property %s', name, e.property_name)
            return False


class ICalendarFile(File):
    """Handle for ICalendar files."""

    content_type = 'text/calendar'

    def __init__(self, content, content_type):
        super(ICalendarFile, self).__init__(content, content_type)
        self._calendar = None

    def validate(self):
        """Verify that file contents are valid."""
        cal = self.calendar
        # TODO(jelmer): return the list of errors to the caller
        if cal.is_broken:
            raise InvalidFileContents(
                self.content_type, self.content,
                "Broken calendar file")
        errors = list(validate_calendar(cal, strict=False))
        if errors:
            raise InvalidFileContents(
                self.content_type, self.content,
                ", ".join(errors))

    def normalized(self):
        """Return a normalized version of the file."""
        return [self.calendar.to_ical()]

    @property
    def calendar(self):
        if self._calendar is None:
            try:
                self._calendar = Calendar.from_ical(b''.join(self.content))
            except ValueError as e:
                raise InvalidFileContents(
                    self.content_type, self.content, str(e))
        return self._calendar

    def describe_delta(self, name, previous):
        try:
            lines = list(describe_calendar_delta(
                previous.calendar if previous else None, self.calendar))
        except NotImplementedError:
            lines = []
        if not lines:
            lines = super(ICalendarFile, self).describe_delta(name, previous)
        return lines

    def describe(self, name):
        try:
            subcomponents = self.calendar.subcomponents
        except InvalidFileContents:
            pass
        else:
            for component in subcomponents:
                try:
                    return describe_component(component)
                except KeyError:
                    pass
        return super(ICalendarFile, self).describe(name)

    def get_uid(self):
        """Extract the UID from a VCalendar file.

        :param cal: Calendar, possibly serialized.
        :return: UID
        """
        for component in self.calendar.subcomponents:
            try:
                return component["UID"]
            except KeyError:
                pass
        raise KeyError
