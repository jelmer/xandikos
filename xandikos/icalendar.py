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

"""ICalendar file handling."""

import logging
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from collections.abc import Callable
from typing import Protocol, overload
from zoneinfo import ZoneInfo

import dateutil.rrule
from icalendar.cal import Calendar, Component, component_factory
from icalendar.parser import Parameters
from icalendar.prop import (
    TypesFactory,
    vCategory,
    vDate,
    vDatetime,
    vDDDTypes,
    vDuration,
    vText,
)

from xandikos.store import File, Filter, InvalidFileContents, InsufficientIndexDataError

from . import collation as _mod_collation
from .store.index import IndexDict, IndexKey, IndexValue, IndexValueIterator

TYPES_FACTORY = TypesFactory()


class PropTypes(Protocol):
    """Protocol for icalendar property types that have params."""

    params: Parameters


TzifyFunction = Callable[[datetime], datetime]

# Default expansion limits for recurring events
# These match the server's declared min/max date-time properties
MIN_EXPANSION_TIME = datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)  # 00010101T000000Z
MAX_EXPANSION_TIME = datetime(
    9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc
)  # 99991231T235959Z

# Maximum number of recurrence instances to expand for infinite recurrences
# This prevents resource exhaustion when expanding recurring events with no end date
# Following sabre/dav and Stalwart's approach of limiting to ~3000 instances
MAX_RECURRENCE_INSTANCES = 3000


# Based on RFC5545 section 3.3.11, CONTROL = %x00-08 / %x0A-1F / %x7F
# Control characters are forbidden in TEXT values, EXCEPT:
# - HTAB (\x09) is explicitly allowed
# - LF (\x0A) and CR (\x0D) are allowed because they appear in the parsed
#   representation when the icalendar library unescapes valid \n and \r
#   escape sequences from the iCalendar file (RFC 5545 allows these escapes)
_INVALID_CONTROL_CHARACTERS = [
    chr(i)
    for i in range(0x00, 0x20)  # \x00-\x1F
    if i not in (0x09, 0x0A, 0x0D)  # Allow HTAB, LF, CR
] + [
    chr(0x7F)  # DEL character
]


class MissingProperty(Exception):
    def __init__(self, property_name) -> None:
        super().__init__(f"Property {property_name!r} missing")
        self.property_name = property_name


def validate_calendar(cal, strict=False):
    """Validate a calendar object.

    Args:
      cal: Calendar object
    Returns: iterator over error messages
    """
    yield from validate_component(cal, strict=strict)


# SubIndexDict is like IndexDict, but None can also occur as a key
SubIndexDict = dict[IndexKey | None, IndexValue]


def create_subindexes(indexes: SubIndexDict | IndexDict, base: str) -> SubIndexDict:
    ret: SubIndexDict = {}
    for k, v in indexes.items():
        if k is not None and k.startswith(base + "/"):
            ret[k[len(base) + 1 :]] = v
        elif k == base:
            ret[None] = v
    return ret


def validate_component(comp, strict=False):
    """Validate a calendar component.

    Args:
      comp: Calendar component
    """
    # Check text fields for invalid characters
    for name, value in comp.items():
        if isinstance(value, vText):
            for c in _INVALID_CONTROL_CHARACTERS:
                if c in value:
                    yield "Invalid character {} in field {}".format(
                        c.encode("unicode_escape"),
                        name,
                    )
    if strict:
        for required in comp.required:
            try:
                comp[required]
            except KeyError:
                yield f"Missing required field {required}"
    for subcomp in comp.subcomponents:
        yield from validate_component(subcomp, strict=strict)


def calendar_component_delta(old_cal, new_cal):
    """Find the differences between components in two calendars.

    Args:
      old_cal: Old calendar (can be None)
      new_cal: New calendar (can be None)
    Returns: iterator over (old_component, new_component) tuples (either can be None)
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
                yield (
                    by_idx.get(idx, component_factory[component.name]()),
                    component,
                )
            by_idx.pop(idx, None)
        else:
            yield (old_component, component)
    for old_component in by_idx.values():
        yield (old_component, component_factory[old_component.name]())


def calendar_prop_delta(old_component, new_component):
    fields = set(
        [field for field in old_component or []]
        + [field for field in new_component or []]
    )
    for field in fields:
        old_value = old_component.get(field)
        new_value = new_component.get(field)
        if (
            getattr(old_value, "to_ical", None) is None
            or getattr(new_value, "to_ical", None) is None
            or old_value.to_ical() != new_value.to_ical()
        ):
            yield (field, old_value, new_value)


def describe_component(component):
    if component.name == "VTODO":
        try:
            return f"task '{component['SUMMARY']}'"
        except KeyError:
            return "task"
    else:
        try:
            return component["SUMMARY"]
        except KeyError:
            return "calendar item"


DELTA_IGNORE_FIELDS = {
    "LAST-MODIFIED",
    "SEQUENCE",
    "DTSTAMP",
    "PRODID",
    "CREATED",
    "COMPLETED",
    "X-MOZ-GENERATION",
    "X-LIC-ERROR",
    "UID",
}


def describe_calendar_delta(old_cal, new_cal):
    """Describe the differences between two calendars.

    Args:
      old_cal: Old calendar (can be None)
      new_cal: New calendar (can be None)
    Returns: Lines describing changes
    """
    # TODO(jelmer): Extend
    for old_component, new_component in calendar_component_delta(old_cal, new_cal):
        if not new_component:
            yield f"Deleted {describe_component(old_component)}"
            continue
        description = describe_component(new_component)
        if not old_component:
            yield f"Added {describe_component(new_component)}"
            continue
        for field, old_value, new_value in calendar_prop_delta(
            old_component, new_component
        ):
            if field.upper() in DELTA_IGNORE_FIELDS:
                continue
            if old_component.name.upper() == "VTODO" and field.upper() == "STATUS":
                if new_value is None:
                    yield f"status of {description} deleted"
                else:
                    human_readable = {
                        "NEEDS-ACTION": "needing action",
                        "COMPLETED": "complete",
                        "CANCELLED": "cancelled",
                    }
                    yield f"{description} marked as {human_readable.get(new_value.upper(), new_value)}"
            elif field.upper() == "DESCRIPTION":
                yield f"changed description of {description}"
            elif field.upper() == "SUMMARY":
                yield f"changed summary of {description}"
            elif field.upper() == "LOCATION":
                yield f"changed location of {description} to {new_value}"
            elif (
                old_component.name.upper() == "VTODO"
                and field.upper() == "PERCENT-COMPLETE"
                and new_value is not None
            ):
                yield "%s marked as %d%% completed." % (description, new_value)
            elif field.upper() == "DUE":
                yield "changed due date for {} from {} to {}".format(
                    description,
                    old_value.dt if old_value else "none",
                    new_value.dt if new_value else "none",
                )
            elif field.upper() == "DTSTART":
                yield "changed start date/time of {} from {} to {}".format(
                    description,
                    old_value.dt if old_value else "none",
                    new_value.dt if new_value else "none",
                )
            elif field.upper() == "DTEND":
                yield "changed end date/time of {} from {} to {}".format(
                    description,
                    old_value.dt if old_value else "none",
                    new_value.dt if new_value else "none",
                )
            elif field.upper() == "CLASS":
                yield "changed class of {} from {} to {}".format(
                    description,
                    old_value.lower() if old_value else "none",
                    new_value.lower() if new_value else "none",
                )
            elif field.upper() == "PRIORITY":
                yield "changed priority of {} from {} to {}".format(
                    description,
                    old_value if old_value else "none",
                    new_value if new_value else "none",
                )
            elif field.upper() == "CATEGORIES":
                yield "changed categories of {} from {} to {}".format(
                    description,
                    old_value if old_value else "none",
                    new_value if new_value else "none",
                )
            elif field.upper() == "URL":
                yield "changed URL of {} to {}".format(
                    description,
                    new_value if new_value else "none",
                )
            elif field.upper() == "ORGANIZER":
                yield "changed organizer of {} to {}".format(
                    description,
                    new_value if new_value else "none",
                )
            elif field.upper() == "ATTENDEE":
                yield f"modified attendees for {description}"
            elif field.upper() == "RRULE":
                yield f"changed recurrence rule for {description}"
            elif field.upper() == "EXDATE":
                yield f"modified exception dates for {description}"
            elif field.upper() == "RDATE":
                yield f"modified recurrence dates for {description}"
            elif field.upper() == "DURATION":
                yield "changed duration of {} from {} to {}".format(
                    description,
                    old_value.dt if old_value else "none",
                    new_value.dt if new_value else "none",
                )
            elif field.upper() == "TRANSP":
                transparency_map = {
                    "OPAQUE": "busy",
                    "TRANSPARENT": "free",
                }
                yield "changed transparency of {} from {} to {}".format(
                    description,
                    transparency_map.get(
                        old_value.upper() if old_value else "", old_value or "none"
                    ),
                    transparency_map.get(
                        new_value.upper() if new_value else "", new_value or "none"
                    ),
                )
            else:
                yield f"modified field {field} in {description}"
                logging.debug(
                    "Changed %s/%s or %s/%s from %s to %s.",
                    old_component.name,
                    field,
                    new_component.name,
                    field,
                    old_value,
                    new_value,
                )


def apply_time_range_vevent(start, end, comp, tzify):
    dtstart = comp.get("DTSTART")
    if not dtstart:
        raise MissingProperty("DTSTART")

    if not (end > tzify(dtstart.dt)):
        return False

    dtend = comp.get("DTEND")
    if dtend:
        if tzify(dtend.dt) < tzify(dtstart.dt):
            logging.debug("Invalid DTEND < DTSTART")
        return start < tzify(dtend.dt)

    duration = comp.get("DURATION")
    if duration:
        return start < tzify(dtstart.dt) + duration.dt
    if getattr(dtstart.dt, "time", None) is not None:
        return start <= tzify(dtstart.dt)
    else:
        return start < (tzify(dtstart.dt) + timedelta(1))


def apply_time_range_vjournal(start, end, comp, tzify):
    dtstart = comp.get("DTSTART")
    if not dtstart:
        raise MissingProperty("DTSTART")

    if not (end > tzify(dtstart.dt)):
        return False

    if getattr(dtstart.dt, "time", None) is not None:
        return start <= tzify(dtstart.dt)
    else:
        return start < (tzify(dtstart.dt) + timedelta(1))


def apply_time_range_vtodo(start, end, comp, tzify):
    dtstart = comp.get("DTSTART")
    due = comp.get("DUE")

    # See RFC4719, section 9.9
    if dtstart:
        duration = comp.get("DURATION")
        if duration and not due:
            return start <= tzify(dtstart.dt) + duration.dt and (
                end > tzify(dtstart.dt) or end >= tzify(dtstart.dt) + duration.dt
            )
        elif due and not duration:
            return (start <= tzify(dtstart.dt) or start < tzify(due.dt)) and (
                end > tzify(dtstart.dt) or end < tzify(due.dt)
            )
        else:
            return start <= tzify(dtstart.dt) and end > tzify(dtstart.dt)

    if due:
        return start < tzify(due.dt) and end >= tzify(due.dt)

    completed = comp.get("COMPLETED")
    created = comp.get("CREATED")
    if completed:
        if created:
            return (start <= tzify(created.dt) or start <= tzify(completed.dt)) and (
                end >= tzify(created.dt) or end >= tzify(completed.dt)
            )
        else:
            return start <= tzify(completed.dt) and end >= tzify(completed.dt)
    elif created:
        return end >= tzify(created.dt)
    else:
        return True


def apply_time_range_vfreebusy(start, end, comp, tzify):
    dtstart = comp.get("DTSTART")
    dtend = comp.get("DTEND")
    if dtstart and dtend:
        return start <= tzify(dtend.dt) and end > tzify(dtstart.dt)

    for period in comp.get("FREEBUSY", []):
        if start < period.end and end > period.start:
            return True

    return False


def _create_enriched_valarm(alarm: Component, parent: Component) -> Component:
    """Create a modified VALARM component with calculated absolute trigger time.

    This creates a new VALARM that converts relative triggers (e.g., "-PT15M")
    to absolute trigger times based on the parent component's DTSTART/DUE properties.
    This enrichment is necessary for time-range filtering to work correctly with
    relative triggers, and must be applied consistently in both filtering and indexing.

    Args:
        alarm: The VALARM component to enrich
        parent: The parent component (VEVENT/VTODO) containing timing information

    Returns:
        A new VALARM component with absolute TRIGGER if applicable, otherwise unchanged
    """
    from icalendar.cal import Alarm

    # Create a new alarm component
    enriched = Alarm()

    # Copy all properties from the original alarm except TRIGGER
    for key in alarm:
        if key != "TRIGGER":
            enriched[key] = alarm[key]

    # Copy subcomponents
    for subcomp in alarm.subcomponents:
        enriched.add_component(subcomp)

    # Handle TRIGGER conversion
    trigger = alarm.get("TRIGGER")
    if trigger and isinstance(trigger.dt, timedelta):
        # Convert relative trigger to absolute
        related = trigger.params.get("RELATED", "START")

        if related == "START":
            base_time = parent.get("DTSTART")
            if base_time:
                absolute_time = base_time.dt + trigger.dt
                # Create new absolute trigger
                enriched.add("TRIGGER", vDDDTypes(absolute_time))
        elif related == "END":
            # For VEVENT, use DTEND or DTSTART + DURATION
            # For VTODO, use DUE or DTSTART + DURATION
            if parent.name == "VEVENT":
                end_time = parent.get("DTEND")
                if not end_time:
                    start_time = parent.get("DTSTART")
                    duration = parent.get("DURATION")
                    if start_time and duration:
                        end_time_dt = start_time.dt + duration.dt
                    else:
                        # No end time determinable, keep original trigger
                        enriched["TRIGGER"] = trigger
                        return enriched
                else:
                    end_time_dt = end_time.dt
            elif parent.name == "VTODO":
                end_time = parent.get("DUE")
                if not end_time:
                    start_time = parent.get("DTSTART")
                    duration = parent.get("DURATION")
                    if start_time and duration:
                        end_time_dt = start_time.dt + duration.dt
                    else:
                        # No end time determinable, keep original trigger
                        enriched["TRIGGER"] = trigger
                        return enriched
                else:
                    end_time_dt = end_time.dt
            else:
                # Unknown parent type, keep original trigger
                enriched["TRIGGER"] = trigger
                return enriched

            absolute_time = end_time_dt + trigger.dt
            # Create new absolute trigger
            enriched.add("TRIGGER", vDDDTypes(absolute_time))
        else:
            # Unknown RELATED value, keep original trigger
            enriched["TRIGGER"] = trigger
    else:
        # Already absolute or missing, keep as is
        if trigger:
            enriched["TRIGGER"] = trigger

    return enriched


def apply_time_range_valarm(start, end, comp, tzify):
    """Check if VALARM overlaps with the given time range.

    According to RFC 4791, a VALARM is said to overlap a time range if:
    (start <= trigger-time) AND (end > trigger-time)

    For repeating alarms, it overlaps if any trigger instance overlaps.

    NOTE: This function expects the VALARM to have been enriched with
    absolute trigger times when it has relative triggers.
    """
    # Get the trigger property
    trigger = comp.get("TRIGGER")
    if not trigger:
        return False

    # Handle both absolute and relative triggers
    if isinstance(trigger.dt, timedelta):
        # This is a relative trigger (timedelta) - we can't determine overlap
        # without parent component context
        raise TypeError(
            "Cannot determine overlap for VALARM with relative trigger "
            "without parent component context. Use enriched VALARM with "
            "absolute trigger time instead."
        )

    # Get the trigger time (absolute)
    trigger_time = tzify(trigger.dt)

    # Check if the trigger time overlaps with the time range
    if start <= trigger_time and end > trigger_time:
        return True

    # Check for repeating alarms
    repeat_count = comp.get("REPEAT")
    duration = comp.get("DURATION")

    if repeat_count and duration:
        # Calculate each repetition
        for i in range(1, int(repeat_count) + 1):
            repeat_time = trigger_time + (duration.dt * i)
            if start <= repeat_time and end > repeat_time:
                return True

    return False


def apply_time_range_vavailability(start, end, comp, tzify):
    """Check if VAVAILABILITY overlaps with the given time range.

    According to RFC 7953, section 7.2.2, a VAVAILABILITY component overlaps
    a time range based on DTSTART, DTEND, and DURATION properties.
    """
    dtstart = comp.get("DTSTART")
    dtend = comp.get("DTEND")
    duration = comp.get("DURATION")

    # Case 1: Both DTSTART and DTEND are present
    if dtstart and dtend:
        return start < tzify(dtend.dt) and end > tzify(dtstart.dt)

    # Case 2: DTSTART and DURATION are present
    if dtstart and duration:
        dtend_calc = tzify(dtstart.dt) + duration.dt
        return start < dtend_calc and end > tzify(dtstart.dt)

    # Case 3: Only DTSTART is present
    if dtstart:
        return end > tzify(dtstart.dt)

    # Case 4: Only DTEND is present
    if dtend:
        return start < tzify(dtend.dt)

    # Case 5: No time properties - always matches
    return True


def apply_time_range_available(start, end, comp, tzify):
    """Check if AVAILABLE subcomponent overlaps with the given time range.

    AVAILABLE components within VAVAILABILITY follow similar rules to VAVAILABILITY.
    """
    # Same logic as VAVAILABILITY
    return apply_time_range_vavailability(start, end, comp, tzify)


class PropertyTimeRangeMatcher:
    def __init__(self, start: datetime, end: datetime) -> None:
        self.start = start
        self.end = end

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.start!r}, {self.end!r})"

    def match(self, prop, tzify):
        dt = tzify(prop.dt)
        return dt >= self.start and dt <= self.end

    def match_indexes(
        self, prop: SubIndexDict, tzify: TzifyFunction, context: str | None = None
    ):
        """Match indexes against this property time range matcher.

        Args:
            prop: Property index dictionary to match against
            tzify: Timezone conversion function
            context: Optional context string (e.g. filename) for error/warning reporting (unused here)
        """
        return any(
            self.match(vDDDTypes(vDDDTypes.from_ical(p.decode("utf-8"))), tzify)
            for p in prop[None]
            if not isinstance(p, bool)
        )


TimeRangeFilter = Callable[[datetime, datetime, Component | dict, TzifyFunction], bool]


class ComponentTimeRangeMatcher:
    all_props = [
        "DTSTART",
        "DTEND",
        "DURATION",
        "CREATED",
        "COMPLETED",
        "DUE",
        "FREEBUSY",
    ]

    # According to https://tools.ietf.org/html/rfc4791, section 9.9 these
    # are the properties to check.
    component_handlers: dict[str, TimeRangeFilter] = {
        "VEVENT": apply_time_range_vevent,
        "VTODO": apply_time_range_vtodo,
        "VJOURNAL": apply_time_range_vjournal,
        "VFREEBUSY": apply_time_range_vfreebusy,
        "VALARM": apply_time_range_valarm,
        "VAVAILABILITY": apply_time_range_vavailability,
        "AVAILABLE": apply_time_range_available,
    }

    def __init__(self, start, end, comp=None) -> None:
        self.start = start
        self.end = end
        self.comp = comp

    def __repr__(self) -> str:
        if self.comp is not None:
            return f"{self.__class__.__name__}({self.start!r}, {self.end!r}, comp={self.comp!r})"
        else:
            return f"{self.__class__.__name__}({self.start!r}, {self.end!r})"

    def match(self, comp: Component, tzify: TzifyFunction):
        if comp.name is None:
            raise ValueError("Component has no name in time-range filter")
        try:
            component_handler = self.component_handlers[comp.name]
        except KeyError:
            logging.warning("unknown component %r in time-range filter", comp.name)
            return False
        return component_handler(self.start, self.end, comp, tzify)

    def match_indexes(
        self, indexes: SubIndexDict, tzify: TzifyFunction, context: str | None = None
    ):
        """Match indexes against this time range matcher.

        Args:
            indexes: Index dictionary to match against
            tzify: Timezone conversion function
            context: Optional context string (e.g. filename) for error/warning reporting
        """
        # Check if we have RRULE - if so, expand and test occurrences
        rrule_values = indexes.get("P=RRULE")
        if rrule_values and rrule_values[0]:
            return self._match_indexes_with_rrule(indexes, tzify, context)

        # Original logic for non-recurring events
        vs: list[dict[str, vDDDTypes | None]] = []
        # Handle edge case where recurring events have inconsistent DTEND/DURATION properties
        # by finding the maximum number of occurrences across all properties
        max_occurrences = 0
        for name, values in indexes.items():
            if name and name.startswith("P=") and name[2:] in self.all_props:
                max_occurrences = max(max_occurrences, len(values))

        for i in range(max_occurrences):
            d: dict[str, vDDDTypes | None] = {}
            for name, values in indexes.items():
                if not name:
                    continue
                field = name[2:]
                if field in self.all_props:
                    try:
                        value = values[i]
                    except IndexError:
                        # This property doesn't have a value at this index
                        # This is expected when events have inconsistent properties
                        continue
                    else:
                        if isinstance(value, bool):
                            continue
                        if field == "DURATION":
                            d[field] = vDDDTypes(
                                vDuration.from_ical(value.decode("utf-8"))
                            )
                        else:
                            d[field] = vDDDTypes(
                                vDDDTypes.from_ical(value.decode("utf-8"))
                            )
            # Include any entry that has time properties
            if d:
                vs.append(d)

        try:
            component_handler = self.component_handlers[self.comp]
        except KeyError:
            logging.warning("unknown component %r in time-range filter", self.comp)
            return False

        # If we have no valid entries from indexes, raise exception to indicate
        # that we cannot determine the result from index data alone
        if not vs:
            raise InsufficientIndexDataError(
                "No valid index entries found for time-range filtering"
            )

        for v in vs:
            if component_handler(self.start, self.end, v, tzify):
                return True
        return False

    def _match_indexes_with_rrule(
        self, indexes: SubIndexDict, tzify: TzifyFunction, context: str | None = None
    ):
        """Handle time-range matching for recurring events using RRULE expansion.

        Args:
            indexes: Index dictionary to match against
            tzify: Timezone conversion function
            context: Optional context string (e.g. filename) for error/warning reporting
        """
        # Extract and validate RRULE and DTSTART from indexes
        rrule_values = indexes.get("P=RRULE", [])
        dtstart_values = indexes.get("P=DTSTART", [])

        if (
            not rrule_values
            or not dtstart_values
            or not rrule_values[0]
            or not dtstart_values[0]
        ):
            return False

        def decode_bytes(value: bytes, field_name: str) -> str:
            if not isinstance(value, bytes):
                raise TypeError(f"Expected bytes for {field_name}, got {type(value)}")
            return value.decode("utf-8")

        # Type narrowing: we've checked these are not None/False above
        rrule_value = rrule_values[0]
        dtstart_value = dtstart_values[0]
        assert isinstance(rrule_value, bytes)
        assert isinstance(dtstart_value, bytes)

        try:
            rrule_str = decode_bytes(rrule_value, "RRULE")
            dtstart_str = decode_bytes(dtstart_value, "DTSTART")

            # Parse DTSTART and create rrule
            dtstart_parsed = vDDDTypes.from_ical(dtstart_str)
            rrule = dateutil.rrule.rrulestr(rrule_str, dtstart=dtstart_parsed)
        except (TypeError, ValueError) as e:
            # If RRULE parsing fails, log with context and return False
            uid_values = indexes.get("P=UID", [])
            uid = (
                decode_bytes(uid_values[0], "UID")
                if uid_values and uid_values[0] and isinstance(uid_values[0], bytes)
                else "unknown"
            )

            if context:
                logging.warning(
                    "Failed to parse RRULE in time-range filter for %s (UID=%s): %s",
                    context,
                    uid,
                    e,
                )
            else:
                logging.warning(
                    "Failed to parse RRULE in time-range filter (UID=%s): %s", uid, e
                )
            return False

        # Get component handler for testing occurrences
        try:
            component_handler = self.component_handlers[self.comp]
        except KeyError:
            logging.warning("unknown component %r in time-range filter", self.comp)
            return False

        # Calculate event duration for boundary adjustment
        event_duration = self._calculate_event_duration(
            indexes, dtstart_parsed, decode_bytes
        )

        # Generate occurrences within the time range
        query_start = self.start - (event_duration or timedelta(0))
        occurrences = self._get_occurrences_in_range(
            rrule, dtstart_parsed, query_start, self.end
        )

        # Test each occurrence against the time range
        return self._test_occurrences(
            occurrences,
            indexes,
            event_duration,
            component_handler,
            tzify,
            decode_bytes,
        )

    def _calculate_event_duration(
        self, indexes: SubIndexDict, dtstart_parsed, decode_bytes
    ):
        """Calculate event duration from DURATION or DTEND properties."""
        duration_values = indexes.get("P=DURATION", [])
        dtend_values = indexes.get("P=DTEND", [])

        if duration_values and duration_values[0]:
            duration_value = duration_values[0]
            if isinstance(duration_value, bytes):
                duration_str = decode_bytes(duration_value, "DURATION")
                return vDuration.from_ical(duration_str)
        elif dtend_values and dtend_values[0]:
            dtend_value = dtend_values[0]
            if isinstance(dtend_value, bytes):
                dtend_str = decode_bytes(dtend_value, "DTEND")
                dtend_parsed_val = vDDDTypes.from_ical(dtend_str)
                if isinstance(dtstart_parsed, datetime) and isinstance(
                    dtend_parsed_val, datetime
                ):
                    return dtend_parsed_val - dtstart_parsed
        return None

    def _get_occurrences_in_range(self, rrule, dtstart_parsed, query_start, query_end):
        """Generate RRULE occurrences within the specified time range."""
        # Normalize query bounds to match the original DTSTART type/timezone
        start_normalized = _normalize_dt_for_rrule(query_start, dtstart_parsed)
        end_normalized = _normalize_dt_for_rrule(query_end, dtstart_parsed)

        # For date-only events, extend the end bound to include the full day
        if isinstance(dtstart_parsed, date) and not isinstance(
            dtstart_parsed, datetime
        ):
            end_normalized = end_normalized + timedelta(days=1)

        # When the query end is unbounded (at MAX_EXPANSION_TIME), limit the number
        # of instances to prevent resource exhaustion with infinite recurrences
        # Compare dates to handle both aware and naive datetimes
        query_end_date = (
            query_end.date() if isinstance(query_end, datetime) else query_end
        )
        max_date = MAX_EXPANSION_TIME.date()
        if query_end_date >= max_date:
            # Use xafter with count limit for unbounded queries
            occurrences = list(
                rrule.xafter(start_normalized, count=MAX_RECURRENCE_INSTANCES, inc=True)
            )
            # Filter to only those before end_normalized
            return [occ for occ in occurrences if occ <= end_normalized]
        else:
            return list(rrule.between(start_normalized, end_normalized, inc=True))

    def _test_occurrences(
        self,
        occurrences,
        indexes,
        event_duration,
        component_handler,
        tzify,
        decode_bytes,
    ):
        """Test each occurrence against the time range filter."""

        class MockProperty:
            def __init__(self, dt_value):
                self.dt = dt_value

        duration_values = indexes.get("P=DURATION", [])

        for occurrence in occurrences:
            # Create occurrence dictionary for component handler
            if isinstance(occurrence, date) and not isinstance(occurrence, datetime):
                occurrence_dt = datetime.combine(occurrence, time()).replace(
                    tzinfo=timezone.utc
                )
                occurrence_dict = {"DTSTART": MockProperty(occurrence_dt)}
            else:
                occurrence_dict = {"DTSTART": MockProperty(occurrence)}

            # Add DTEND or DURATION to the occurrence
            if duration_values and duration_values[0]:
                duration_value = duration_values[0]
                if isinstance(duration_value, bytes):
                    duration_str = decode_bytes(duration_value, "DURATION")
                    duration_obj = vDuration.from_ical(duration_str)
                    occurrence_dict["DURATION"] = MockProperty(duration_obj)
            elif event_duration:
                occurrence_dict["DTEND"] = MockProperty(occurrence + event_duration)

            # Test this occurrence against the time range
            if component_handler(self.start, self.end, occurrence_dict, tzify):
                return True
        return False

    def index_keys(self) -> list[list[str]]:
        if self.comp == "VEVENT":
            props = ["DTSTART", "DTEND", "DURATION", "RRULE"]
        elif self.comp == "VTODO":
            props = ["DTSTART", "DUE", "DURATION", "CREATED", "COMPLETED"]
        elif self.comp == "VJOURNAL":
            props = ["DTSTART"]
        elif self.comp == "VFREEBUSY":
            props = ["DTSTART", "DTEND", "FREEBUSY"]
        elif self.comp == "VALARM":
            # VALARM properties used for time-range calculation
            props = ["TRIGGER", "DURATION", "REPEAT"]
        else:
            props = self.all_props
        return [["P=" + prop] for prop in props]


class TextMatcher:
    def __init__(
        self,
        name: str,
        text: str,
        collation: str | None = None,
        negate_condition: bool = False,
        match_type: str = "contains",
    ) -> None:
        self.name = name
        self.type_fn = TYPES_FACTORY.for_property(name)
        assert isinstance(text, str)
        self.text = text
        if collation is None:
            collation = "i;ascii-casemap"
        self.collation = _mod_collation.get_collation(collation)
        self.negate_condition = negate_condition
        self.match_type = match_type

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.name!r}, {self.text!r}, "
            f"collation={self.collation!r}, negate_condition={self.negate_condition!r})"
        )

    def match_indexes(self, indexes: SubIndexDict):
        return any(
            self.match(self.type_fn(self.type_fn.from_ical(k))) for k in indexes[None]
        )

    def match(self, prop: vText | vCategory | str):
        if isinstance(prop, vText):
            matches = self.collation(str(prop), self.text, self.match_type)
        elif isinstance(prop, str):
            matches = self.collation(prop, self.text, self.match_type)
        elif isinstance(prop, vCategory):
            matches = any([self.match(cat) for cat in prop.cats])
        else:
            logging.warning(
                "potentially unsupported value in text match search: " + repr(prop)
            )
            return False
        if self.negate_condition:
            return not matches
        else:
            return matches


class ComponentFilter:
    time_range: ComponentTimeRangeMatcher | None

    def __init__(
        self, name: str, children=None, is_not_defined: bool = False, time_range=None
    ) -> None:
        self.name = name
        self.children = children
        self.is_not_defined = is_not_defined
        self.time_range = time_range
        self.children = children or []

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.name!r}, children={self.children!r}, "
            f"is_not_defined={self.is_not_defined!r}, time_range={self.time_range!r})"
        )

    def filter_subcomponent(
        self,
        name: str,
        is_not_defined: bool = False,
        time_range: ComponentTimeRangeMatcher | None = None,
    ):
        ret = ComponentFilter(
            name=name, is_not_defined=is_not_defined, time_range=time_range
        )
        self.children.append(ret)
        return ret

    def filter_property(
        self,
        name: str,
        is_not_defined: bool = False,
        time_range: PropertyTimeRangeMatcher | None = None,
    ):
        ret = PropertyFilter(
            name=name, is_not_defined=is_not_defined, time_range=time_range
        )
        self.children.append(ret)
        return ret

    def filter_time_range(self, start: datetime, end: datetime):
        self.time_range = ComponentTimeRangeMatcher(start, end, comp=self.name)
        return self.time_range

    def _find_time_range(self):
        """Recursively find the first time range in this filter or its children."""
        if self.time_range:
            return self.time_range

        for child in self.children:
            if isinstance(child, ComponentFilter):
                nested_range = child._find_time_range()
                if nested_range:
                    return nested_range
        return None

    def match(self, comp: Component, tzify: TzifyFunction):
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
        if self.time_range is not None and not self.time_range.match(comp, tzify):
            return False

        # ... and all specified CALDAV:prop-filter and CALDAV:comp-filter child
        # XML elements also match the targeted calendar component;
        for child in self.children:
            if isinstance(child, ComponentFilter):
                subcomponents = self._get_subcomponents_for_matching(child, comp)
                if not any(child.match(c, tzify) for c in subcomponents):
                    return False
            elif isinstance(child, PropertyFilter):
                if not child.match(comp, tzify):
                    return False
            else:
                raise TypeError(child)

        return True

    def _get_subcomponents_for_matching(
        self, child_filter: "ComponentFilter", parent_comp: Component
    ) -> list[Component]:
        """Get subcomponents for matching, with special handling for VALARM.

        When filtering VALARM components with time-range, we need to enrich them
        by converting relative TRIGGER values to absolute times based on the parent
        component's timing properties.
        """
        if child_filter.name == "VALARM" and child_filter.time_range is not None:
            # Create enriched VALARM components with absolute trigger times
            return [
                _create_enriched_valarm(c, parent_comp)
                for c in parent_comp.subcomponents
                if c.name == "VALARM"
            ]
        else:
            return parent_comp.subcomponents

    def _implicitly_defined(self):
        return any(
            not getattr(child, "is_not_defined", False) for child in self.children
        )

    def match_indexes(
        self, indexes: IndexDict, tzify: TzifyFunction, context: str | None = None
    ):
        """Match indexes against this component filter.

        Args:
            indexes: Index dictionary to match against
            tzify: Timezone conversion function
            context: Optional context string (e.g. filename) for error/warning reporting
        """
        myindex = "C=" + self.name
        if self.is_not_defined:
            return not bool(indexes[myindex])

        subindexes = create_subindexes(indexes, myindex)

        if self.time_range is not None and not self.time_range.match_indexes(
            subindexes, tzify, context
        ):
            return False

        for child in self.children:
            if not child.match_indexes(subindexes, tzify, context):
                return False

        if not self._implicitly_defined():
            if myindex not in indexes:
                raise InsufficientIndexDataError(f"Missing component index: {myindex}")
            return bool(indexes[myindex])

        return True

    def index_keys(self):
        mine = "C=" + self.name
        for child in self.children + ([self.time_range] if self.time_range else []):
            for tl in child.index_keys():
                yield [(mine + "/" + child_index) for child_index in tl]
        if not self._implicitly_defined():
            yield [mine]


class PropertyFilter:
    def __init__(
        self,
        name: str,
        children=None,
        is_not_defined: bool = False,
        time_range: PropertyTimeRangeMatcher | None = None,
    ) -> None:
        self.name = name
        self.is_not_defined = is_not_defined
        self.children = children or []
        self.time_range = time_range

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.name!r}, children={self.children!r}, "
            f"is_not_defined={self.is_not_defined!r}, time_range={self.time_range!r})"
        )

    def filter_parameter(
        self, name: str, is_not_defined: bool = False
    ) -> "ParameterFilter":
        ret = ParameterFilter(name=name, is_not_defined=is_not_defined)
        self.children.append(ret)
        return ret

    def filter_time_range(
        self, start: datetime, end: datetime
    ) -> PropertyTimeRangeMatcher:
        self.time_range = PropertyTimeRangeMatcher(start, end)
        return self.time_range

    def filter_text_match(
        self,
        text: str,
        collation: str | None = None,
        negate_condition: bool = False,
        match_type: str = "contains",
    ) -> TextMatcher:
        ret = TextMatcher(
            self.name,
            text,
            collation=collation,
            negate_condition=negate_condition,
            match_type=match_type,
        )
        self.children.append(ret)
        return ret

    def match(self, comp: Component, tzify: TzifyFunction) -> bool:
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

    def match_indexes(
        self, indexes: SubIndexDict, tzify: TzifyFunction, context: str | None = None
    ) -> bool:
        """Match indexes against this property filter.

        Args:
            indexes: Index dictionary to match against
            tzify: Timezone conversion function
            context: Optional context string (e.g. filename) for error/warning reporting
        """
        myindex = "P=" + self.name
        if self.is_not_defined:
            return not bool(indexes[myindex])
        subindexes: SubIndexDict = create_subindexes(indexes, myindex)
        if not self.children and not self.time_range:
            return bool(indexes[myindex])

        if self.time_range is not None and not self.time_range.match_indexes(
            subindexes, tzify, context
        ):
            return False

        for child in self.children:
            if not child.match_indexes(subindexes):
                return False

        return True

    def index_keys(self):
        mine = "P=" + self.name
        for child in self.children:
            if not isinstance(child, ParameterFilter):
                continue
            for tl in child.index_keys():
                yield [(mine + "/" + child_index) for child_index in tl]
        yield [mine]


class ParameterFilter:
    children: list[TextMatcher]

    def __init__(
        self,
        name: str,
        children: list[TextMatcher] | None = None,
        is_not_defined: bool = False,
    ) -> None:
        self.name = name
        self.is_not_defined = is_not_defined
        self.children = children or []

    def filter_text_match(
        self,
        text: str,
        collation: str | None = None,
        negate_condition: bool = False,
        match_type: str = "contains",
    ) -> TextMatcher:
        ret = TextMatcher(
            self.name,
            text,
            collation=collation,
            negate_condition=negate_condition,
            match_type=match_type,
        )
        self.children.append(ret)
        return ret

    def match(self, prop: PropTypes) -> bool:
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

    def index_keys(self) -> Iterable[list[str]]:
        yield ["A=" + self.name]

    def match_indexes(self, indexes: IndexDict) -> bool:
        myindex = "A=" + self.name
        if self.is_not_defined:
            return not bool(indexes[myindex])

        subindexes = create_subindexes(indexes, myindex)

        if not subindexes:
            return False

        for child in self.children:
            if not child.match_indexes(subindexes):
                return False
        return True


class CalendarFilter(Filter):
    """A filter that works on ICalendar files."""

    content_type = "text/calendar"

    def __init__(self, default_timezone: str | timezone) -> None:
        self.tzify = lambda dt: as_tz_aware_ts(dt, default_timezone)
        self.children: list[ComponentFilter] = []

    def filter_subcomponent(self, name, is_not_defined=False, time_range=None):
        ret = ComponentFilter(
            name=name, is_not_defined=is_not_defined, time_range=time_range
        )
        self.children.append(ret)
        return ret

    def _find_time_range(self):
        """Recursively find the first time range in component filters."""
        for child in self.children:
            if isinstance(child, ComponentFilter):
                if child.time_range:
                    return child.time_range
                # Recursively check nested filters
                nested_range = child._find_time_range()
                if nested_range:
                    return nested_range
        return None

    def check(self, name: str, file: File) -> bool:
        if not isinstance(file, ICalendarFile):
            return False

        # Look for time range in component filters (including nested ones)
        time_range = self._find_time_range()

        # Expand with time constraints if needed
        if time_range:
            c = file.get_expanded_calendar(time_range.start, time_range.end)
        else:
            # For unbounded queries, use the original calendar without expansion
            # to avoid infinite expansion of recurring events
            c = file.calendar

        if c is None:
            return False

        for child_filter in self.children:
            try:
                if not child_filter.match(c, self.tzify):
                    return False
            except MissingProperty as e:
                logging.warning(
                    "calendar_query: Ignoring calendar object %s, due "
                    "to missing property %s",
                    name,
                    e.property_name,
                )
                return False
        return True

    def check_from_indexes(self, name: str, indexes: IndexDict) -> bool:
        for child_filter in self.children:
            try:
                if not child_filter.match_indexes(indexes, self.tzify, name):  # type: ignore
                    return False
            except MissingProperty as e:
                logging.warning(
                    "calendar_query: Ignoring calendar object %s, due "
                    "to missing property %s",
                    name,
                    e.property_name,
                )
                return False
        return True

    def index_keys(self) -> list[list[str]]:
        result = []
        for child in self.children:
            result.extend(child.index_keys())
        return result

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.children!r})"


class ICalendarFile(File):
    """Handle for ICalendar files."""

    content_type = "text/calendar"

    def __init__(self, content, content_type) -> None:
        super().__init__(content, content_type)
        self._calendar = None

    def validate(self) -> None:
        """Verify that file contents are valid."""
        cal = self.calendar
        if cal.errors:
            raise InvalidFileContents(
                self.content_type,
                self.content,
                "Broken calendar file: " + ", ".join(cal.errors),
            )
        errors = list(validate_calendar(cal, strict=False))
        if errors:
            raise InvalidFileContents(
                self.content_type, self.content, ", ".join(errors)
            )

    def normalized(self):
        """Return a normalized version of the file."""
        return [self.calendar.to_ical()]

    @property
    def calendar(self):
        if self._calendar is None:
            try:
                self._calendar = Calendar.from_ical(b"".join(self.content))
            except ValueError as exc:
                raise InvalidFileContents(
                    self.content_type, self.content, str(exc)
                ) from exc
        return self._calendar

    def get_expanded_calendar(self, start=None, end=None):
        """Get calendar with recurring events expanded within the given time range.

        Args:
            start: Start datetime for expansion (defaults to MIN_EXPANSION_TIME)
            end: End datetime for expansion (defaults to MAX_EXPANSION_TIME)

        Returns:
            Calendar with recurring events expanded
        """
        if start is None:
            start = MIN_EXPANSION_TIME
        if end is None:
            end = MAX_EXPANSION_TIME

        return expand_calendar_rrule(self.calendar, start, end)

    def describe_delta(self, name, previous):
        try:
            lines = list(
                describe_calendar_delta(
                    previous.calendar if previous else None, self.calendar
                )
            )
        except NotImplementedError:
            lines = []
        if not lines:
            lines = super().describe_delta(name, previous)
        return lines

    def describe(self, name):
        try:
            subcomponents = self.calendar.subcomponents
        except InvalidFileContents:
            # Calendar has invalid contents, skip description
            pass
        else:
            for component in subcomponents:
                try:
                    return component["SUMMARY"]
                except KeyError:
                    pass
        return super().describe(name)

    def get_uid(self):
        """Extract the UID from a VCalendar file.

        Args:
          cal: Calendar, possibly serialized.
        Returns: UID
        """
        for component in self.calendar.subcomponents:
            try:
                return component["UID"]
            except KeyError:
                pass
        raise KeyError

    def _get_index(self, key: IndexKey) -> IndexValueIterator:
        # Track parent component for VALARM enrichment
        # Use the original calendar without expansion for indexing
        # RRULE expansion will be handled at query time in match_indexes()
        todo: list[tuple[Component, list[str], Component | None]] = [
            (self.calendar, key.split("/"), None)
        ]
        rest: list[tuple[Component, list[str], Component | None]] = []
        c: Component
        while todo:
            (c, segments, parent) = todo.pop(0)
            if segments and segments[0].startswith("C="):
                if c.name == segments[0][2:]:
                    if len(segments) > 1 and segments[1].startswith("C="):
                        # Pass current component as parent for subcomponents
                        todo.extend((comp, segments[1:], c) for comp in c.subcomponents)
                    else:
                        rest.append((c, segments[1:], parent))

        for c, segments, parent in rest:
            if not segments:
                yield True
            elif segments[0].startswith("P="):
                assert len(segments) == 1
                prop_name = segments[0][2:]
                try:
                    p = c[prop_name]
                except KeyError:
                    pass
                else:
                    if p is not None:
                        ical = p.to_ical()
                        # Special handling for VALARM TRIGGER property
                        if (
                            c.name == "VALARM"
                            and prop_name == "TRIGGER"
                            and parent is not None
                            and isinstance(p.dt, timedelta)
                        ):
                            # Create enriched VALARM to get absolute trigger time.
                            # This ensures index values match what the filter will see,
                            # preventing "index based filter not matching real file filter" errors.
                            enriched = _create_enriched_valarm(c, parent)
                            if "TRIGGER" in enriched:
                                ical = enriched["TRIGGER"].to_ical()
                        yield ical
            else:
                raise AssertionError(f"segments: {segments!r}")


def as_tz_aware_ts(dt: datetime | date, default_timezone: str | timezone) -> datetime:
    if not getattr(dt, "time", None):
        _dt = datetime.combine(dt, time())
    else:
        _dt = dt  # type: ignore
    if _dt.tzinfo is None:
        if isinstance(default_timezone, str):
            _dt = _dt.replace(tzinfo=ZoneInfo(default_timezone))
        else:
            _dt = _dt.replace(tzinfo=default_timezone)
    assert _dt.tzinfo
    return _dt


@overload
def _normalize_to_dtstart_type(
    dt_value: date | datetime, dtstart: datetime
) -> datetime: ...


@overload
def _normalize_to_dtstart_type(dt_value: date | datetime, dtstart: date) -> date: ...


def _normalize_to_dtstart_type(
    dt_value: date | datetime, dtstart: date | datetime
) -> date | datetime:
    """Normalize a date/datetime value to match the type of DTSTART.

    This is necessary because dateutil.rrule cannot compare date and datetime objects.
    When adding EXDATE/RDATE values to an rruleset, they must be the same type as DTSTART.

    Args:
        dt_value: The date or datetime value to normalize
        dtstart: The DTSTART value to match the type of

    Returns:
        The normalized value matching DTSTART's type
    """
    # If both are the same type, check timezone compatibility
    if type(dt_value) is type(dtstart):
        # Both are datetimes - ensure timezone awareness matches
        if isinstance(dt_value, datetime) and isinstance(dtstart, datetime):
            if dt_value.tzinfo is not None and dtstart.tzinfo is None:
                # Converting aware to naive - extract date and use dtstart's time
                return datetime.combine(dt_value.date(), dtstart.time())
            elif dt_value.tzinfo is None and dtstart.tzinfo is not None:
                # Make dt_value aware to match dtstart
                return dt_value.replace(tzinfo=dtstart.tzinfo)
        return dt_value

    # If DTSTART is a date (not datetime), convert datetime to date
    if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
        if isinstance(dt_value, datetime):
            return dt_value.date()
        return dt_value

    # If DTSTART is a datetime, convert date to datetime
    if isinstance(dtstart, datetime):
        if isinstance(dt_value, date) and not isinstance(dt_value, datetime):
            # Convert date to datetime, matching DTSTART's time and timezone
            # This ensures that EXDATE;VALUE=DATE:20240102 matches the occurrence
            # at DTSTART's time (e.g., 10:00:00), not just midnight
            if dtstart.tzinfo is not None:
                # Use the same time and timezone as DTSTART
                return datetime.combine(dt_value, dtstart.time()).replace(
                    tzinfo=dtstart.tzinfo
                )
            else:
                # Naive datetime - use DTSTART's time
                return datetime.combine(dt_value, dtstart.time())
        # dt_value is already a datetime, but check timezone awareness
        if isinstance(dt_value, datetime):
            if dt_value.tzinfo is not None and dtstart.tzinfo is None:
                # Converting aware datetime to naive datetime
                # First extract the date to handle timezone properly, then
                # combine with dtstart's time to create a naive datetime
                return datetime.combine(dt_value.date(), dtstart.time())
            elif dt_value.tzinfo is None and dtstart.tzinfo is not None:
                # Make dt_value aware to match dtstart
                return dt_value.replace(tzinfo=dtstart.tzinfo)
        return dt_value

    return dt_value


def rruleset_from_comp(comp: Component) -> dateutil.rrule.rruleset:
    dtstart = comp["DTSTART"].dt
    rrulestr = comp["RRULE"].to_ical().decode("utf-8")
    rrule = dateutil.rrule.rrulestr(rrulestr, dtstart=dtstart)
    rs = dateutil.rrule.rruleset()
    rs.rrule(rrule)  # type: ignore

    # dateutil.rrule internally converts date objects to datetime objects.
    # To determine what type the rrule will generate, we check the first occurrence.
    # This is necessary because EXDATE/RDATE values must match the generated type.
    first_occurrence = next(iter(rrule), None)
    effective_dtstart: datetime
    if first_occurrence is not None:
        effective_dtstart = first_occurrence
    elif isinstance(dtstart, date) and not isinstance(dtstart, datetime):
        # dateutil.rrule converts date to datetime at midnight
        effective_dtstart = datetime.combine(dtstart, datetime.min.time())
    else:
        # dtstart must be a datetime at this point
        assert isinstance(dtstart, datetime)
        effective_dtstart = dtstart

    if "EXDATE" in comp:
        exdate_prop = comp["EXDATE"]
        # EXDATE can be either:
        # 1. A single vDDDLists (one EXDATE property with one or more dates)
        # 2. A list of vDDDLists (multiple EXDATE properties)
        # Extract the actual datetime/date values from the .dts list(s)
        # and normalize them to match what the rrule will generate
        if isinstance(exdate_prop, list):
            for exdate_list in exdate_prop:
                for exdate in exdate_list.dts:
                    normalized = _normalize_to_dtstart_type(
                        exdate.dt, effective_dtstart
                    )
                    rs.exdate(normalized)
        else:
            for exdate in exdate_prop.dts:
                normalized = _normalize_to_dtstart_type(exdate.dt, effective_dtstart)
                rs.exdate(normalized)
    if "RDATE" in comp:
        rdate_prop = comp["RDATE"]
        # RDATE can be either:
        # 1. A single vDDDLists (one RDATE property with one or more dates)
        # 2. A list of vDDDLists (multiple RDATE properties)
        # Extract the actual datetime/date values from the .dts list(s)
        # and normalize them to match what the rrule will generate
        if isinstance(rdate_prop, list):
            for rdate_list in rdate_prop:
                for rdate in rdate_list.dts:
                    normalized = _normalize_to_dtstart_type(rdate.dt, effective_dtstart)
                    rs.rdate(normalized)
        else:
            for rdate in rdate_prop.dts:
                normalized = _normalize_to_dtstart_type(rdate.dt, effective_dtstart)
                rs.rdate(normalized)
    if "EXRULE" in comp:
        exrulestr = comp["EXRULE"].to_ical().decode("utf-8")
        exrule = dateutil.rrule.rrulestr(exrulestr, dtstart=dtstart)
        assert isinstance(exrule, dateutil.rrule.rrule)
        rs.exrule(exrule)
    return rs


def _get_event_duration(comp: Component) -> timedelta | None:
    """Get the duration of an event component."""
    if "DURATION" in comp:
        return comp["DURATION"].dt
    elif "DTEND" in comp and "DTSTART" in comp:
        return comp["DTEND"].dt - comp["DTSTART"].dt
    return None


def _normalize_dt_for_rrule(
    dt: date | datetime, original_dt: date | datetime
) -> datetime:
    """Normalize a datetime for rrule operations based on the original event type.

    The rrule library requires the search bounds to match the type of the original DTSTART:
    - For date-only events, use datetime at midnight
    - For floating time events, use naive datetimes
    - For timezone-aware events, use aware datetimes
    """
    # Handle date-only events - convert to datetime at midnight
    if not isinstance(original_dt, datetime):
        if isinstance(dt, datetime):
            return datetime.combine(dt.date(), time.min)
        return datetime.combine(dt, time.min)

    # Handle datetime events (both naive and aware)
    if isinstance(dt, datetime):
        # Match the timezone awareness of the original
        if original_dt.tzinfo is None and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        elif original_dt.tzinfo is not None and dt.tzinfo is None:
            # This shouldn't happen with our current code, but handle it gracefully
            return dt.replace(tzinfo=original_dt.tzinfo)
        return dt

    # If dt is a date but original_dt is datetime, convert to datetime
    return datetime.combine(dt, time.min)


def _event_overlaps_range(comp: Component, start, end) -> bool:
    """Check if a calendar component overlaps with a time range."""
    # Use UTC as default timezone for consistency with existing code
    default_tz = timezone.utc

    def tzify(dt):
        return as_tz_aware_ts(dt, default_tz)

    # Use the appropriate time range filter based on component type
    component_handlers = {
        "VEVENT": apply_time_range_vevent,
        "VTODO": apply_time_range_vtodo,
        "VJOURNAL": apply_time_range_vjournal,
        "VFREEBUSY": apply_time_range_vfreebusy,
        "VALARM": apply_time_range_valarm,
        "VAVAILABILITY": apply_time_range_vavailability,
        "AVAILABLE": apply_time_range_available,
    }

    if comp.name and comp.name in component_handlers:
        handler = component_handlers[comp.name]
        # Normalize start and end to the same timezone as component values
        start_normalized = tzify(start)
        end_normalized = tzify(end)
        return handler(start_normalized, end_normalized, comp, tzify)

    # For unknown component types, require DTSTART
    if "DTSTART" not in comp:
        return False

    # Fallback for other component types with DTSTART
    event_start = tzify(comp["DTSTART"].dt)

    # Calculate event end time
    if "DTEND" in comp:
        event_end = tzify(comp["DTEND"].dt)
    elif "DURATION" in comp:
        event_end = event_start + comp["DURATION"].dt
    else:
        # Default duration
        if isinstance(comp["DTSTART"].dt, datetime):
            event_end = event_start
        else:
            event_end = event_start + timedelta(days=1)

    # Normalize start and end for comparison
    start_normalized = tzify(start)
    end_normalized = tzify(end)

    return event_start < end_normalized and event_end > start_normalized


def _expand_rrule_component(
    incomp: Component,
    start: datetime | None = None,
    end: datetime | None = None,
    existing: dict[str | date | datetime, Component] = {},
) -> Iterable[Component]:
    if "RRULE" not in incomp:
        return

    rs = rruleset_from_comp(incomp)
    original_dtstart = incomp["DTSTART"]

    # Create base component without recurrence fields
    base_comp = incomp.copy()
    for field in ["RRULE", "EXRULE", "UNTIL", "RDATE", "EXDATE"]:
        if field in base_comp:
            del base_comp[field]

    # Get occurrences from rrule
    if start is not None and end is not None:
        # Adjust start backwards by event duration to catch overlapping events
        duration = _get_event_duration(incomp)
        adjusted_start = start - duration if duration else start

        # Normalize datetimes for rrule operations
        start_normalized = _normalize_dt_for_rrule(adjusted_start, original_dtstart.dt)
        end_normalized = _normalize_dt_for_rrule(end, original_dtstart.dt)

        # When the query end is unbounded (at MAX_EXPANSION_TIME), limit the number
        # of instances to prevent resource exhaustion with infinite recurrences
        # Compare dates to handle both aware and naive datetimes
        end_date = end.date() if isinstance(end, datetime) else end
        max_date = MAX_EXPANSION_TIME.date()
        if end_date >= max_date:
            # Use xafter with count limit for unbounded queries
            all_occurrences = list(
                rs.xafter(start_normalized, count=MAX_RECURRENCE_INSTANCES, inc=True)
            )
            # Filter to only those before end_normalized
            occurrences = [occ for occ in all_occurrences if occ <= end_normalized]
        else:
            occurrences = rs.between(start_normalized, end_normalized, inc=True)
    else:
        # For unbounded queries, we still need to return a list/iterator
        occurrences = rs  # type: ignore

    for ts in occurrences:
        # Normalize timestamp based on original event type
        if not isinstance(original_dtstart.dt, datetime):
            ts_normalized = ts.date()
            ts_for_dtstart = ts.date()
        else:
            ts_normalized = asutc(ts)
            ts_for_dtstart = ts

        # Check if this is an exception event
        try:
            outcomp = existing.pop(ts_normalized)
        except KeyError:
            # Create new occurrence
            outcomp = base_comp.copy()

            # Set new DTSTART
            new_dtstart = create_prop_from_date_or_datetime(ts_for_dtstart)
            try:
                if original_dtstart.params:
                    new_dtstart.params = original_dtstart.params.copy()
            except AttributeError:
                pass
            outcomp["DTSTART"] = new_dtstart

            # Update DTEND if present
            if "DTEND" in outcomp:
                original_duration = incomp["DTEND"].dt - original_dtstart.dt
                new_dtend = create_prop_from_date_or_datetime(
                    ts_for_dtstart + original_duration
                )
                try:
                    if incomp["DTEND"].params:
                        new_dtend.params = incomp["DTEND"].params.copy()
                except AttributeError:
                    pass
                outcomp["DTEND"] = new_dtend

        # Check if occurrence overlaps with time range
        if start is not None and end is not None:
            if not _event_overlaps_range(outcomp, start, end):
                continue

        # Set RECURRENCE-ID
        outcomp["RECURRENCE-ID"] = create_prop_from_date_or_datetime(ts_normalized)
        yield outcomp


def expand_calendar_rrule(
    incal: Calendar, start: datetime | None = None, end: datetime | None = None
) -> Calendar:
    outcal = Calendar()
    if incal.name != "VCALENDAR":
        raise AssertionError(f"called on file with root component {incal.name}")

    # Copy calendar properties
    for field in incal:
        outcal[field] = incal[field]

    # Collect exception events (components with RECURRENCE-ID)
    exceptions = {}
    for comp in incal.subcomponents:
        if "RECURRENCE-ID" in comp:
            ts = asutc(comp["RECURRENCE-ID"].dt)
            exceptions[ts] = comp

    # Process all components
    for comp in incal.subcomponents:
        if comp.name == "VTIMEZONE":
            # Always include timezone definitions
            outcal.add_component(comp)
        elif "RECURRENCE-ID" in comp:
            # Skip - handled separately
            pass
        elif "RRULE" in comp:
            # Expand recurring events
            for expanded in _expand_rrule_component(comp, start, end, exceptions):
                outcal.add_component(expanded)
        else:
            # Include non-recurring events
            outcal.add_component(comp)

    # Add remaining exception events that fall within the time range
    if start is not None and end is not None:
        for exc_comp in exceptions.values():
            if _event_overlaps_range(exc_comp, start, end):
                outcal.add_component(exc_comp)

    return outcal


def limit_calendar_recurrence_set(
    incal: Calendar, start: datetime, end: datetime
) -> Calendar:
    """Limit recurrence set to a specified time range.

    Unlike expand_calendar_rrule, this preserves the master component with RRULE intact
    and only includes overridden instances (RECURRENCE-ID) that fall within or affect
    the specified time range.

    Args:
        incal: Input calendar
        start: Start of time range (UTC)
        end: End of time range (UTC)

    Returns:
        Calendar with master component and relevant overridden instances
    """
    outcal = Calendar()
    if incal.name != "VCALENDAR":
        raise AssertionError(f"called on file with root component {incal.name}")

    # Copy calendar properties
    for field in incal:
        outcal[field] = incal[field]

    # Normalize start/end to naive UTC for comparison
    start_utc = asutc(start) if isinstance(start, datetime) else start
    end_utc = asutc(end) if isinstance(end, datetime) else end

    # First, add all VTIMEZONE components to preserve timezone definitions
    for insub in incal.subcomponents:
        if insub.name == "VTIMEZONE":
            outcal.add_component(insub)

    # Process other components
    for insub in incal.subcomponents:
        if insub.name == "VTIMEZONE":
            continue

        if "RECURRENCE-ID" not in insub:
            # This is a master component - always include it
            outcal.add_component(insub)
        else:
            # This is an overridden instance - check if it's relevant to the time range
            recurrence_id = insub["RECURRENCE-ID"].dt

            # Include if the overridden instance falls within the time range
            # or if it affects instances that would fall within the range
            # (e.g., THISANDFUTURE modifications)

            # Convert to UTC for comparison if needed
            if isinstance(recurrence_id, datetime):
                rec_utc = asutc(recurrence_id)
            else:
                rec_utc = recurrence_id

            # Check if this instance should be included
            include = False

            # 1. Check if the recurrence-id itself is within range
            # For date comparisons, convert datetime bounds to dates
            if isinstance(rec_utc, date) and not isinstance(rec_utc, datetime):
                # Compare dates
                start_date = (
                    start_utc.date() if isinstance(start_utc, datetime) else start_utc
                )
                end_date = end_utc.date() if isinstance(end_utc, datetime) else end_utc
                if start_date <= rec_utc <= end_date:
                    include = True
            else:
                # Compare datetimes
                if start_utc <= rec_utc <= end_utc:
                    include = True

            # 2. Check if this is a THISANDFUTURE modification that affects the range
            range_param = insub.get("RECURRENCE-ID").params.get("RANGE")
            if range_param and range_param.upper() == "THISANDFUTURE":
                # This modification affects all instances from recurrence_id onwards
                if isinstance(rec_utc, date) and not isinstance(rec_utc, datetime):
                    end_date = (
                        end_utc.date() if isinstance(end_utc, datetime) else end_utc
                    )
                    if rec_utc <= end_date:
                        include = True
                else:
                    if rec_utc <= end_utc:
                        include = True

            # 3. Check if the actual instance times overlap the range
            if not include:
                # Get the actual start/end times of this instance
                if "DTSTART" in insub:
                    dtstart = insub["DTSTART"].dt
                    if isinstance(dtstart, datetime):
                        dtstart_utc = asutc(dtstart)
                    else:
                        dtstart_utc = dtstart

                    if "DTEND" in insub:
                        dtend = insub["DTEND"].dt
                        if isinstance(dtend, datetime):
                            dtend_utc = asutc(dtend)
                        else:
                            dtend_utc = dtend
                    elif "DURATION" in insub:
                        duration = insub["DURATION"].dt
                        dtend_utc = dtstart_utc + duration
                    else:
                        # No explicit end time - treat as instant event
                        dtend_utc = dtstart_utc

                    # Check if the instance overlaps with the requested range
                    # Handle date vs datetime comparisons
                    if isinstance(dtstart_utc, date) and not isinstance(
                        dtstart_utc, datetime
                    ):
                        start_date = (
                            start_utc.date()
                            if isinstance(start_utc, datetime)
                            else start_utc
                        )
                        end_date = (
                            end_utc.date() if isinstance(end_utc, datetime) else end_utc
                        )
                        if dtstart_utc < end_date and dtend_utc > start_date:
                            include = True
                    else:
                        if dtstart_utc < end_utc and dtend_utc > start_utc:
                            include = True

            if include:
                outcal.add_component(insub)

    return outcal


def limit_calendar_freebusy_set(
    incal: Calendar, start: datetime, end: datetime
) -> Calendar:
    """Limit FREEBUSY properties to a specified time range.

    Filters FREEBUSY properties in VFREEBUSY components to only include
    those that overlap with the specified time range. This implements
    RFC 4791 section 9.6.7.

    Args:
        incal: Input calendar
        start: Start of time range (UTC)
        end: End of time range (UTC)

    Returns:
        Calendar with VFREEBUSY components containing only overlapping FREEBUSY periods
    """
    outcal = Calendar()
    if incal.name != "VCALENDAR":
        raise AssertionError(f"called on file with root component {incal.name}")

    # Copy calendar properties
    for field in incal:
        outcal[field] = incal[field]

    # Normalize start/end to naive UTC for comparison
    start_utc = asutc(start) if isinstance(start, datetime) else start
    end_utc = asutc(end) if isinstance(end, datetime) else end

    # First, add all VTIMEZONE components to preserve timezone definitions
    for insub in incal.subcomponents:
        if insub.name == "VTIMEZONE":
            outcal.add_component(insub)

    # Process other components
    for insub in incal.subcomponents:
        if insub.name == "VTIMEZONE":
            continue

        if insub.name == "VFREEBUSY":
            # Create a new VFREEBUSY component with filtered FREEBUSY properties
            from icalendar.cal import FreeBusy

            newsub = FreeBusy()

            # Copy all non-FREEBUSY properties
            for field in insub:
                if field != "FREEBUSY":
                    newsub[field] = insub[field]

            # Filter and copy only overlapping FREEBUSY properties
            freebusy_props = insub.get("FREEBUSY", [])
            if not isinstance(freebusy_props, list):
                freebusy_props = [freebusy_props]

            for fb_period in freebusy_props:
                # FREEBUSY properties are vPeriod objects with start and end times
                # Check if the period overlaps with the requested range
                # Overlap occurs if: period_start < range_end AND period_end > range_start
                period_start_utc = (
                    asutc(fb_period.start)
                    if isinstance(fb_period.start, datetime)
                    else fb_period.start
                )
                period_end_utc = (
                    asutc(fb_period.end)
                    if isinstance(fb_period.end, datetime)
                    else fb_period.end
                )

                if period_start_utc < end_utc and period_end_utc > start_utc:
                    # This FREEBUSY period overlaps with the requested range
                    newsub.add("FREEBUSY", fb_period)

            # Copy subcomponents (though VFREEBUSY typically doesn't have any)
            for subcomp in insub.subcomponents:
                newsub.add_component(subcomp)

            outcal.add_component(newsub)
        else:
            # For non-VFREEBUSY components, just copy them as-is
            outcal.add_component(insub)

    return outcal


def asutc(dt):
    if isinstance(dt, date) and not isinstance(dt, datetime):
        # Return date as-is - dates are timezone-agnostic
        return dt
    if dt.tzinfo is None:
        # Naive datetime - return as-is
        return dt
    # Convert to UTC and make naive for consistent comparison
    return dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def create_prop_from_date_or_datetime(dt):
    """Create appropriate vDate or vDatetime property based on input type."""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return vDate(dt)
    else:
        return vDatetime(dt)
