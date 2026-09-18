# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""iTIP (RFC 5546) message construction, validation, and delivery.

The CalDAV scheduling protocol (RFC 6638) is built on top of iTIP. This
module owns the iTIP-shaped pieces — building CANCEL/REPLY messages,
parsing/validating REQUEST messages, deriving the schedule-tag
signature from iTIP-relevant properties — separately from the CalDAV
plumbing in :mod:`xandikos.scheduling` that exposes them over HTTP.
"""

import datetime
import hashlib

from icalendar.cal import Calendar, Component, FreeBusy
from icalendar.prop import vDDDTypes, vPeriod

from xandikos.caldav import PRODID
from xandikos.icalendar import PropTypes, TimeProperty


# RFC 5546 §3.6 / RFC 6638 §6.2 request-status codes used in iTIP REPLY
# messages and CalDAV schedule-response replies.
REQUEST_STATUS_SUCCESS = "2.0;Success"
REQUEST_STATUS_INVALID_CALENDAR_USER = "3.7;Invalid calendar user"
REQUEST_STATUS_NO_AUTHORITY = "3.8;No authority"
REQUEST_STATUS_SERVICE_UNAVAILABLE = "5.0;Service unavailable"
# RFC 6638 §3.2 SCHEDULE-STATUS codes: 1.1 marks a message handed to an
# external transport (iMIP), 5.1 marks a transport-side failure.
REQUEST_STATUS_SENT = "1.1;Sent"
REQUEST_STATUS_TRANSPORT_UNAVAILABLE = "5.1;Service unavailable"


# Properties whose values participate in iTIP scheduling. The schedule-tag
# (RFC 6638 §3.2.10) only changes when one of these changes within a
# scheduling-bearing component; bookkeeping properties such as DTSTAMP,
# LAST-MODIFIED, and CREATED do not affect it.
SCHEDULING_PROPERTIES = frozenset(
    {
        "ATTENDEE",
        "ORGANIZER",
        "DTSTART",
        "DTEND",
        "DUE",
        "DURATION",
        "RRULE",
        "RDATE",
        "EXDATE",
        "RECURRENCE-ID",
        "SEQUENCE",
        "STATUS",
        "SUMMARY",
        "LOCATION",
        "DESCRIPTION",
        "PRIORITY",
        "TRANSP",
        "CLASS",
        "URL",
        "CATEGORIES",
        "RESOURCES",
        "PERCENT-COMPLETE",
        "REQUEST-STATUS",
    }
)


# ATTENDEE parameters that carry participation status rather than the
# substance of the invitation. RFC 6638 3.2.10 requires the schedule-tag
# to stay put when a resource is updated by automatically processing a
# scheduling message that only changes these, so they are excluded from
# the signature the tag is derived from.
PARTICIPATION_STATUS_PARAMS = frozenset(
    {"PARTSTAT", "RSVP", "SCHEDULE-STATUS", "SCHEDULE-AGENT", "SCHEDULE-FORCE-SEND"}
)


# Components that carry scheduling state. Other component types (VTIMEZONE,
# VALARM, VFREEBUSY responses inside replies, etc.) are intentionally skipped
# so they do not destabilise the tag.
SCHEDULING_COMPONENTS = frozenset({"VEVENT", "VTODO", "VJOURNAL"})


class InvalidSchedulingRequest(Exception):
    """The body submitted as an iTIP request is not well-formed."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


def _serialize_scheduling_value(value: PropTypes) -> bytes:
    """Serialise a single iCalendar property value, including its parameters.

    Plain ``to_ical()`` would drop parameters such as ``PARTSTAT`` on
    ATTENDEE, which is exactly the kind of state the schedule-tag must
    track. We fold params and value into one sorted, opaque byte string.
    """
    return _serialize_params(value.params, value.to_ical())


def _serialize_params(params, rendered: bytes) -> bytes:
    """Prefix *rendered* with *params*, sorted for stability."""
    if not params:
        return rendered
    # Parameter names are case-insensitive; normalise to upper for stability.
    param_items = sorted(
        (k.upper().encode("ascii"), str(v).encode("utf-8")) for k, v in params.items()
    )
    return b";".join(b"=".join(item) for item in param_items) + b":" + rendered


def extract_scheduling_signature(
    cal: Calendar,
    mask_own_attendee_params: "frozenset[str] | None" = None,
    skip_attendees: "frozenset[str] | None" = None,
    mask_attendee_status: bool = False,
) -> bytes:
    """Compute a stable signature of the scheduling-relevant content in *cal*.

    Two calendars with the same signature are considered equivalent for the
    purposes of CalDAV scheduling: a PUT that only changes properties outside
    SCHEDULING_PROPERTIES (or properties on non-scheduling components) yields
    the same signature, and therefore the same schedule-tag.

    Args:
      cal: parsed icalendar Calendar object.
      mask_own_attendee_params: if given, ATTENDEE entries whose value
        is in this set have their parameters dropped from the signature.
        Used by the attendee-write check (RFC 6638 §3.1) to ignore the
        user's own PARTSTAT/COMMENT/RSVP changes when deciding whether
        the rest of the event has been touched.
      skip_attendees: if given, ATTENDEE entries whose value is in this
        set are dropped from the signature entirely (presence as well
        as params). Used by the attendee-write check to allow adding
        delegates: an attendee may add an ATTENDEE entry whose
        DELEGATED-FROM matches their own address (RFC 6638 §3.2.6).
      mask_attendee_status: drop PARTICIPATION_STATUS_PARAMS from every
        ATTENDEE. Used for the schedule-tag, which RFC 6638 §3.2.10
        requires to stay put across a PARTSTAT-only update applied by
        the server from a scheduling message.

    Returns: opaque ``bytes`` value suitable for hashing or direct comparison.
    """
    components: list[tuple[bytes, list[tuple[bytes, list[bytes]]]]] = []
    for component in cal.subcomponents:
        if component.name is None:
            continue
        name = component.name.upper()
        if name not in SCHEDULING_COMPONENTS:
            continue
        try:
            uid = component["UID"].to_ical()
        except KeyError:
            uid = b""
        else:
            if isinstance(uid, str):
                uid = uid.encode("utf-8")
        try:
            recurrence_id = component["RECURRENCE-ID"].to_ical()
        except KeyError:
            recurrence_id = b""
        else:
            if isinstance(recurrence_id, str):
                recurrence_id = recurrence_id.encode("utf-8")
        props: list[tuple[bytes, list[bytes]]] = []
        for field in component:
            if field.upper() not in SCHEDULING_PROPERTIES:
                continue
            value = component.get(field)
            if value is None:
                continue
            if field.upper() == "ATTENDEE":
                values = value if isinstance(value, list) else [value]
                items = [
                    _serialize_attendee_value(
                        v, mask_own_attendee_params, mask_attendee_status
                    )
                    for v in values
                    if skip_attendees is None or str(v) not in skip_attendees
                ]
                if not items:
                    continue
            elif isinstance(value, list):
                items = [_serialize_scheduling_value(v) for v in value]
            else:
                items = [_serialize_scheduling_value(value)]
            items.sort()
            props.append((field.upper().encode("ascii"), items))
        props.sort()
        components.append(
            (name.encode("ascii") + b":" + uid + b":" + recurrence_id, props)
        )
    components.sort()

    h = hashlib.sha256()
    for comp_key, props in components:
        h.update(b"C\x00")
        h.update(comp_key)
        h.update(b"\x00")
        for field_name, items in props:
            h.update(b"P\x00")
            h.update(field_name)
            h.update(b"\x00")
            for item in items:
                h.update(b"V\x00")
                h.update(item)
                h.update(b"\x00")
    return h.digest()


def _serialize_attendee_value(
    value: PropTypes,
    mask_own: "frozenset[str] | None",
    mask_status: bool = False,
) -> bytes:
    """Like _serialize_scheduling_value but drops params when masked.

    Used by extract_scheduling_signature to ignore the user's own
    PARTSTAT/RSVP/etc. when checking whether anything *else* has
    changed. With *mask_status*, the participation-status parameters are
    dropped from every ATTENDEE rather than just the user's own.
    """
    if mask_own is not None and str(value) in mask_own:
        return value.to_ical()
    if mask_status:
        params = {
            k: v
            for k, v in value.params.items()
            if k.upper() not in PARTICIPATION_STATUS_PARAMS
        }
        return _serialize_params(params, value.to_ical())
    return _serialize_scheduling_value(value)


def build_itip_cancel(cal: Component) -> Calendar:
    """Build a METHOD:CANCEL VCALENDAR for *cal*.

    Per RFC 5546 §3.2.5, an iTIP CANCEL re-sends the scheduling
    components from the original event, with SEQUENCE bumped by one,
    DTSTAMP set to "now", and STATUS:CANCELLED on each component.
    Non-scheduling components (VTIMEZONE, etc.) are passed through.
    """
    out = Calendar()
    out["VERSION"] = "2.0"
    out["PRODID"] = PRODID
    out["METHOD"] = "CANCEL"
    now = datetime.datetime.now(datetime.timezone.utc)
    for comp in cal.subcomponents:
        clone = comp.copy()
        if clone.name in SCHEDULING_COMPONENTS:
            clone["DTSTAMP"] = vDDDTypes(now)
            try:
                seq = int(comp.get("SEQUENCE", 0))
            except (TypeError, ValueError):
                seq = 0
            clone["SEQUENCE"] = seq + 1
            clone["STATUS"] = "CANCELLED"
        out.add_component(clone)
    return out


def build_itip_request(cal: Component) -> Calendar:
    """Build a METHOD:REQUEST VCALENDAR from *cal*.

    Per RFC 5546 §3.2.2, an iTIP REQUEST carries the organiser's view
    of an event to its attendees. We refresh DTSTAMP on each scheduling
    component but leave SEQUENCE alone — bumping SEQUENCE on material
    changes is the organiser's job, not the transport's. STATUS is
    preserved (CONFIRMED, TENTATIVE, …); only CANCEL forces it.
    Non-scheduling components (VTIMEZONE, etc.) are passed through.
    """
    out = Calendar()
    out["VERSION"] = "2.0"
    out["PRODID"] = PRODID
    out["METHOD"] = "REQUEST"
    now = datetime.datetime.now(datetime.timezone.utc)
    for comp in cal.subcomponents:
        clone = comp.copy()
        if clone.name in SCHEDULING_COMPONENTS:
            clone["DTSTAMP"] = vDDDTypes(now)
        out.add_component(clone)
    return out


def build_itip_reply(cal: Component, attendee_address: str) -> Calendar:
    """Build a METHOD:REPLY VCALENDAR for *attendee_address*.

    Per RFC 5546 §3.2.3, an iTIP REPLY carries one attendee's
    participation status back to the organiser. The reply re-uses each
    scheduling component but narrows ATTENDEE to a single entry —
    the replying attendee's own line, complete with its PARTSTAT and
    other parameters — so the organiser sees only the response they
    asked for. ORGANIZER is preserved as the routing target. SEQUENCE
    is preserved (the organiser owns it); DTSTAMP is refreshed.

    Components where *attendee_address* doesn't appear in ATTENDEE are
    skipped — the reply only carries components the user is actually
    answering for. Non-scheduling components (VTIMEZONE, etc.) are
    passed through unchanged.
    """
    out = Calendar()
    out["VERSION"] = "2.0"
    out["PRODID"] = PRODID
    out["METHOD"] = "REPLY"
    now = datetime.datetime.now(datetime.timezone.utc)
    for comp in cal.subcomponents:
        if comp.name not in SCHEDULING_COMPONENTS:
            out.add_component(comp.copy())
            continue
        own_attendee = _find_attendee(comp, attendee_address)
        if own_attendee is None:
            continue
        clone = comp.copy()
        clone["DTSTAMP"] = vDDDTypes(now)
        # Drop every ATTENDEE then add back just the replying user's.
        del clone["ATTENDEE"]
        clone.add("ATTENDEE", own_attendee)
        out.add_component(clone)
    return out


def _find_attendee(comp: Component, address: str) -> PropTypes | None:
    """Return the ATTENDEE entry for *address* in *comp*, or None."""
    attendees = comp.get("ATTENDEE", [])
    if not isinstance(attendees, list):
        attendees = [attendees]
    for a in attendees:
        if str(a) == address:
            return a
    return None


def validate_freebusy_request(cal: Component) -> Component:
    """Return the single VFREEBUSY in *cal* if the request is well formed."""
    method = cal.get("METHOD")
    if str(method).upper() != "REQUEST":
        raise InvalidSchedulingRequest(
            "Schedule-outbox requests require METHOD:REQUEST"
        )
    fbs = [c for c in cal.subcomponents if c.name == "VFREEBUSY"]
    others = [
        c.name for c in cal.subcomponents if c.name not in ("VFREEBUSY", "VTIMEZONE")
    ]
    if others:
        raise InvalidSchedulingRequest(
            f"Free-busy request must contain only VFREEBUSY, got {others!r}"
        )
    if len(fbs) != 1:
        raise InvalidSchedulingRequest(
            f"Free-busy request must contain exactly one VFREEBUSY, got {len(fbs)}"
        )
    fb = fbs[0]
    if "ORGANIZER" not in fb:
        raise InvalidSchedulingRequest("VFREEBUSY missing ORGANIZER")
    if "ATTENDEE" not in fb:
        raise InvalidSchedulingRequest("VFREEBUSY missing ATTENDEE")
    if "DTSTART" not in fb or "DTEND" not in fb:
        raise InvalidSchedulingRequest("VFREEBUSY missing DTSTART/DTEND")
    return fb


def parse_freebusy_window(
    fb: Component,
) -> tuple[datetime.datetime, datetime.datetime]:
    """Return (start, end) for a VFREEBUSY component as UTC datetimes."""
    start_prop = fb["DTSTART"]
    end_prop = fb["DTEND"]
    assert isinstance(start_prop, TimeProperty)
    assert isinstance(end_prop, TimeProperty)
    start = start_prop.dt
    end = end_prop.dt
    assert isinstance(start, datetime.date | datetime.datetime)
    assert isinstance(end, datetime.date | datetime.datetime)
    if not isinstance(start, datetime.datetime):
        start = datetime.datetime.combine(start, datetime.time(), datetime.timezone.utc)
    if not isinstance(end, datetime.datetime):
        end = datetime.datetime.combine(end, datetime.time(), datetime.timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=datetime.timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=datetime.timezone.utc)
    return start, end


def build_freebusy_reply(
    organizer,
    recipient: str,
    request_comp: Component,
    start: datetime.datetime,
    end: datetime.datetime,
    periods: list[vPeriod],
) -> Calendar:
    """Build a METHOD:REPLY VCALENDAR with the per-recipient VFREEBUSY."""
    cal = Calendar()
    cal["VERSION"] = "2.0"
    cal["PRODID"] = PRODID
    cal["METHOD"] = "REPLY"
    fb = FreeBusy()
    fb["DTSTAMP"] = vDDDTypes(datetime.datetime.now(datetime.timezone.utc))
    fb["DTSTART"] = vDDDTypes(start)
    fb["DTEND"] = vDDDTypes(end)
    if organizer is not None:
        fb["ORGANIZER"] = organizer
    fb["ATTENDEE"] = recipient
    if "UID" in request_comp:
        fb["UID"] = request_comp["UID"]
    if periods:
        fb["FREEBUSY"] = periods
    cal.add_component(fb)
    return cal


def itip_uid(itip_message: Calendar) -> str | None:
    """Return the UID of the first scheduling component in *itip_message*."""
    for comp in itip_message.subcomponents:
        if comp.name in SCHEDULING_COMPONENTS:
            uid = comp.get("UID")
            if uid is not None:
                return str(uid)
    return None


def strip_method(itip_message: Calendar) -> Calendar:
    """Return a copy of *itip_message* with METHOD removed.

    Stored calendar objects don't carry METHOD — that's a property of
    iTIP transport messages, not the events themselves (RFC 5545
    §3.4 / RFC 6638 §3.1).
    """
    out = Calendar()
    for k, v in itip_message.items():
        if k.upper() == "METHOD":
            continue
        out[k] = v
    for comp in itip_message.subcomponents:
        out.add_component(comp.copy())
    return out


def preserve_partstats(existing: Calendar, incoming: Calendar) -> Calendar:
    """Mutate *incoming* in place so attendee PARTSTATs survive a re-REQUEST.

    RFC 6638 §3.2.1: when an organiser sends a fresh REQUEST, the
    attendee's prior PARTSTAT must survive. We match attendees across
    components by (UID, RECURRENCE-ID, ATTENDEE address). Returns the
    same *incoming* object for chaining.
    """
    existing_partstats: dict[tuple[str, str, str], str] = {}
    for comp in existing.subcomponents:
        if comp.name not in SCHEDULING_COMPONENTS:
            continue
        uid = str(comp.get("UID", ""))
        rid = str(comp.get("RECURRENCE-ID", ""))
        attendees = comp.get("ATTENDEE", [])
        if not isinstance(attendees, list):
            attendees = [attendees]
        for a in attendees:
            partstat = a.params.get("PARTSTAT")
            if partstat is not None:
                existing_partstats[(uid, rid, str(a))] = str(partstat)

    for comp in incoming.subcomponents:
        if comp.name not in SCHEDULING_COMPONENTS:
            continue
        uid = str(comp.get("UID", ""))
        rid = str(comp.get("RECURRENCE-ID", ""))
        attendees = comp.get("ATTENDEE", [])
        if not isinstance(attendees, list):
            attendees = [attendees]
        for a in attendees:
            prior = existing_partstats.get((uid, rid, str(a)))
            if prior is not None:
                a.params["PARTSTAT"] = prior
    return incoming
