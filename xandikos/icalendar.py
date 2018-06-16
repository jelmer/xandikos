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

import logging

from icalendar.cal import Calendar, component_factory
from icalendar.prop import vText
from xandikos.store import File, InvalidFileContents

# TODO(jelmer): Populate this further based on
# https://tools.ietf.org/html/rfc5545#3.3.11
_INVALID_CONTROL_CHARACTERS = ['\x0c', '\x01']


def validate_calendar(cal, strict=False):
    """Validate a calendar object.

    :param cal: Calendar object
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
            raise InvalidFileContents(self.content_type, self.content)
        if list(validate_calendar(cal, strict=False)):
            raise InvalidFileContents(self.content_type, self.content)

    def normalized(self):
        """Return a normalized version of the file."""
        return [self.calendar.to_ical()]

    @property
    def calendar(self):
        if self._calendar is None:
            try:
                self._calendar = Calendar.from_ical(b''.join(self.content))
            except ValueError:
                raise InvalidFileContents(self.content_type, self.content)
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
