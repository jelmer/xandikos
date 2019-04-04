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
from icalendar.prop import (
    vDatetime,
    vDDDTypes,
    vText,
)
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


def create_subindexes(indexes, base):
    ret = {}
    for k, v in indexes.items():
        if k is not None and k.startswith(base + '/'):
            ret[k[len(base) + 1:]] = v
        elif k == base:
            ret[None] = v
    return ret


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
    dtstart = comp.get('DTSTART')
    if not dtstart:
        raise MissingProperty('DTSTART')

    if not (end > tzify(dtstart.dt)):
        return False

    dtend = comp.get('DTEND')
    if dtend:
        if tzify(dtend.dt) < tzify(dtstart.dt):
            logging.debug('Invalid DTEND < DTSTART')
        return (start < tzify(dtend.dt))

    duration = comp.get('DURATION')
    if duration:
        return (start < tzify(dtstart.dt) + duration.dt)
    if getattr(dtstart.dt, 'time', None) is not None:
        return (start <= tzify(dtstart.dt))
    else:
        return (start < (tzify(dtstart.dt) + datetime.timedelta(1)))


def apply_time_range_vjournal(start, end, comp, tzify):
    dtstart = comp.get('DTSTART')
    if not dtstart:
        raise MissingProperty('DTSTART')

    if not (end > tzify(dtstart.dt)):
        return False

    if getattr(dtstart.dt, 'time', None) is not None:
        return (start <= tzify(dtstart.dt))
    else:
        return (start < (tzify(dtstart.dt) + datetime.timedelta(1)))


def apply_time_range_vtodo(start, end, comp, tzify):
    dtstart = comp.get('DTSTART')
    due = comp.get('DUE')

    # See RFC4719, section 9.9
    if dtstart:
        duration = comp.get('DURATION')
        if duration and not due:
            return (
                start <= tzify(dtstart.dt) + duration.dt and
                (end > tzify(dtstart.dt) or
                 end >= tzify(dtstart.dt) + duration.dt)
            )
        elif due and not duration:
            return (
                (start <= tzify(dtstart.dt) or
                 start < tzify(due.dt)) and
                (end > tzify(dtstart.dt) or
                 end < tzify(due.dt))
            )
        else:
            return (start <= tzify(dtstart.dt) and
                    end > tzify(dtstart.dt))

    if due:
        return start < tzify(due.dt) and end >= tzify(due.dt)

    completed = comp.get('COMPLETED')
    created = comp.get('CREATED')
    if completed:
        if created:
            return (
                (start <= tzify(created.dt) or
                 start <= tzify(completed.dt)) and
                (end >= tzify(created.dt) or
                 end >= tzify(completed.dt))
            )
        else:
            return (
                start <= tzify(completed.dt) and
                end >= tzify(completed.dt)
            )
    elif created:
        return end >= tzify(created.dt)
    else:
        return True


def apply_time_range_vfreebusy(start, end, comp, tzify):
    dtstart = comp.get('DTSTART')
    dtend = comp.get('DTEND')
    if dtstart and dtend:
        return (
            start <= tzify(dtend.dt) and
            end > tzify(dtstart.dt)
        )

    for period in comp.get('FREEBUSY', []):
        if start < period.end and end > period.start:
            return True

    return False


def apply_time_range_valarm(start, end, comp, tzify):
    raise NotImplementedError(apply_time_range_valarm)


class PropertyTimeRangeMatcher(object):

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __repr__(self):
        return "%s(%r, %r)" % (self.__class__.__name__, self.start, self.end)

    def match(self, prop, tzify):
        dt = tzify(prop.dt)
        return (dt >= self.start and dt <= self.end)

    def match_indexes(self, prop, tzify):
        return any(self.match(vDDDTypes(vDatetime.from_ical(p)), tzify)
                   for p in prop[None])


class ComponentTimeRangeMatcher(object):

    all_props = [
        'DTSTART', 'DTEND', 'DURATION', 'CREATED', 'COMPLETED', 'DUE',
        'FREEBUSY']

    # According to https://tools.ietf.org/html/rfc4791, section 9.9 these
    # are the properties to check.
    component_handlers = {
        'VEVENT': apply_time_range_vevent,
        'VTODO': apply_time_range_vtodo,
        'VJOURNAL': apply_time_range_vjournal,
        'VFREEBUSY': apply_time_range_vfreebusy,
        'VALARM': apply_time_range_valarm}

    def __init__(self, start, end, comp=None):
        self.start = start
        self.end = end
        self.comp = comp

    def __repr__(self):
        if self.comp is not None:
            return "%s(%r, %r, comp=%r)" % (
                self.__class__.__name__, self.start, self.end, self.comp)
        else:
            return "%s(%r, %r)" % (
                self.__class__.__name__, self.start, self.end)

    def match(self, comp, tzify):
        try:
            component_handler = self.component_handlers[comp.name]
        except KeyError:
            logging.warning('unknown component %r in time-range filter',
                            comp.name)
            return False
        return component_handler(self.start, self.end, comp, tzify)

    def match_indexes(self, indexes, tzify):
        vs = {}
        for name, value in indexes.items():
            if name and name[2:] in self.all_props:
                if value:
                    if not isinstance(value[0], vDDDTypes):
                        vs[name[2:]] = vDDDTypes(vDatetime.from_ical(value[0]))
                    else:
                        vs[name[2:]] = value[0]

        try:
            component_handler = self.component_handlers[self.comp]
        except KeyError:
            logging.warning('unknown component %r in time-range filter',
                            self.comp)
            return False
        return component_handler(self.start, self.end, vs, tzify)

    def index_keys(self):
        if self.comp == 'VEVENT':
            props = ['DTSTART', 'DTEND', 'DURATION']
        elif self.comp == 'VTODO':
            props = ['DTSTART', 'DUE', 'DURATION', 'CREATED', 'COMPLETED']
        elif self.comp == 'VJOURNAL':
            props = ['DTSTART']
        elif self.comp == 'VFREEBUSY':
            props = ['DTSTART', 'DTEND', 'FREEBUSY']
        elif self.comp == 'VALARM':
            raise NotImplementedError
        else:
            props = self.all_props
        return [['P=' + prop] for prop in props]


class TextMatcher(object):

    def __init__(self, text, collation=None, negate_condition=False):
        if isinstance(text, str):
            text = text.encode()
        self.text = text
        if collation is None:
            collation = 'i;ascii-casemap'
        self.collation = _mod_collation.get_collation(collation)
        self.negate_condition = negate_condition

    def __repr__(self):
        return '%s(%r, collation=%r, negate_condition=%r)' % (
            self.__class__.__name__, self.text, self.collation,
            self.negate_condition)

    def match_indexes(self, indexes):
        return any(self.match(k) for k in indexes[None])

    def match(self, prop):
        if isinstance(prop, vText):
            prop = prop.encode()
        matches = self.collation(self.text, prop)
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

    def __repr__(self):
        return '%s(%r, children=%r, is_not_defined=%r, time_range=%r)' % (
            self.__class__.__name__, self.name, self.children,
            self.is_not_defined, self.time_range)

    def filter_subcomponent(self, name, is_not_defined=False,
                            time_range=None):
        ret = ComponentFilter(
            name=name, is_not_defined=is_not_defined, time_range=time_range)
        self.children.append(ret)
        return ret

    def filter_property(self, name, is_not_defined=False, time_range=None):
        ret = PropertyFilter(
            name=name, is_not_defined=is_not_defined, time_range=time_range)
        self.children.append(ret)
        return ret

    def filter_time_range(self, start, end):
        self.time_range = ComponentTimeRangeMatcher(
            start, end, comp=self.name)
        return self.time_range

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
        if (self.time_range is not None and
                not self.time_range.match(comp, tzify)):
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

    def _implicitly_defined(self):
        return any(not getattr(child, 'is_not_defined', False)
                   for child in self.children)

    def match_indexes(self, indexes, tzify):
        myindex = 'C=' + self.name
        if self.is_not_defined:
            return not bool(indexes[myindex])

        subindexes = create_subindexes(indexes, myindex)

        if (self.time_range is not None and
                not self.time_range.match_indexes(subindexes, tzify)):
            return False

        for child in self.children:
            if not child.match_indexes(subindexes, tzify):
                return False

        if not self._implicitly_defined():
            return bool(indexes[myindex])

        return True

    def index_keys(self):
        mine = 'C=' + self.name
        for child in (
                self.children +
                ([self.time_range] if self.time_range else [])):
            for tl in child.index_keys():
                yield [(mine + '/' + child_index) for child_index in tl]
        if not self._implicitly_defined():
            yield [mine]


class PropertyFilter(object):

    def __init__(self, name, children=None, is_not_defined=False,
                 time_range=None):
        self.name = name
        self.is_not_defined = is_not_defined
        self.children = children or []
        self.time_range = time_range

    def __repr__(self):
        return '%s(%r, children=%r, is_not_defined=%r, time_range=%r)' % (
            self.__class__.__name__, self.name, self.children,
            self.is_not_defined, self.time_range)

    def filter_parameter(self, name, is_not_defined=False):
        ret = ParameterFilter(name=name, is_not_defined=is_not_defined)
        self.children.append(ret)
        return ret

    def filter_time_range(self, start, end):
        self.time_range = PropertyTimeRangeMatcher(start, end)
        return self.time_range

    def filter_text_match(self, text, collation=None, negate_condition=False):
        ret = TextMatcher(
            text, collation=collation, negate_condition=negate_condition)
        self.children.append(ret)
        return ret

    def match(self, comp, tzify):
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

        if self.time_range and not self.time_range.match(prop, tzify):
            return False

        for child in self.children:
            if not child.match(prop):
                return False

        return True

    def match_indexes(self, indexes, tzify):
        myindex = 'P=' + self.name
        if self.is_not_defined:
            return not bool(indexes[myindex])
        subindexes = create_subindexes(indexes, myindex)
        if not self.children and not self.time_range:
            return bool(indexes[myindex])

        if (self.time_range is not None and
                not self.time_range.match_indexes(subindexes, tzify)):
            return False

        for child in self.children:
            if not child.match_indexes(subindexes):
                return False

        return True

    def index_keys(self):
        mine = 'P=' + self.name
        for child in self.children:
            if not isinstance(child, ParameterFilter):
                continue
            for tl in child.index_keys():
                yield [(mine + '/' + child_index) for child_index in tl]
        yield [mine]


class ParameterFilter(object):

    def __init__(self, name, children=None, is_not_defined=False):
        self.name = name
        self.is_not_defined = is_not_defined
        self.children = children or []

    def filter_text_match(self, text, collation=None, negate_condition=False):
        ret = TextMatcher(
            text, collation=collation, negate_condition=negate_condition)
        self.children.append(ret)
        return ret

    def match(self, prop):
        if self.is_not_defined:
            return self.name not in prop.params

        try:
            value = prop.params[self.name].encode()
        except KeyError:
            return False

        for child in self.children:
            if not child.match(value):
                return False
        return True

    def index_keys(self):
        yield ['A=' + self.name]

    def match_indexes(self, indexes):
        myindex = 'A=' + self.name
        if self.is_not_defined:
            return not bool(indexes[myindex])

        try:
            value = indexes[myindex][0]
        except IndexError:
            return False

        for child in self.children:
            if not child.match(value):
                return False
        return True


class CalendarFilter(Filter):
    """A filter that works on ICalendar files."""

    def __init__(self, default_timezone):
        self.tzify = lambda dt: as_tz_aware_ts(dt, default_timezone)
        self.children = []

    def filter_subcomponent(self, name, is_not_defined=False,
                            time_range=None):
        ret = ComponentFilter(
            name=name, is_not_defined=is_not_defined, time_range=time_range)
        self.children.append(ret)
        return ret

    def check(self, name, file):
        if file.content_type != 'text/calendar':
            return False
        c = file.calendar
        if c is None:
            return False

        for child_filter in self.children:
            try:
                if not child_filter.match(file.calendar, self.tzify):
                    return False
            except MissingProperty as e:
                logging.warning(
                    'calendar_query: Ignoring calendar object %s, due '
                    'to missing property %s', name, e.property_name)
                return False
        return True

    def check_from_indexes(self, name, indexes):
        for child_filter in self.children:
            if not child_filter.match_indexes(
                    indexes, self.tzify):
                return False
        return True

    def index_keys(self):
        subindexes = []
        for child in self.children:
            subindexes.extend(child.index_keys())
        return subindexes

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.children)


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

    def _get_index(self, key):
        todo = [(self.calendar, key.split('/'))]
        rest = []
        while todo:
            (c, segments) = todo.pop(0)
            if segments and segments[0].startswith('C='):
                if c.name == segments[0][2:]:
                    if len(segments) > 1 and segments[1].startswith('C='):
                        todo.extend(
                            (comp, segments[1:]) for comp in c.subcomponents)
                    else:
                        rest.append((c, segments[1:]))

        for c, segments in rest:
            if not segments:
                yield True
            elif segments[0].startswith('P='):
                assert len(segments) == 1
                try:
                    yield c[segments[0][2:]]
                except KeyError:
                    pass
            else:
                raise AssertionError('segments: %r' % segments)


def as_tz_aware_ts(dt, default_timezone):
    if not getattr(dt, 'time', None):
        dt = datetime.datetime.combine(dt, datetime.time())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_timezone)
    assert dt.tzinfo
    return dt
