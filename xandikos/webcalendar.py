# Xandikos
# Copyright (C) 2026 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Browser-facing view of CalDAV calendars.

Renders calendar collections as a month grid, individual days as a
list, and individual VEVENT/VTODO resources as edit forms. Form posts
create, update or delete events and tasks.

Mirrors the shape of :mod:`xandikos.webcontacts`: ``render_month``,
``render_day``, ``maybe_render_event`` and ``render_new_event_form``
return the 5-tuple expected by ``webdav.Resource.render``, and
``handle_post`` returns a ``webdav.Response`` when it recognises a
form action (or ``None`` to let the default RFC 5995 add-member path
run for real CalDAV clients).
"""

from __future__ import annotations

import calendar as stdcalendar
import os
import re
import urllib.parse
import uuid
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

import jinja2
from icalendar import Calendar as ICalendar
from icalendar import Event as IEvent
from icalendar import Todo as ITodo

from xandikos import __version__ as xandikos_version
from xandikos import webdav
from xandikos.icalendar import ICalendarFile, expand_calendar_rrule
from xandikos.store import (
    DuplicateUidError,
    InvalidFileContents,
    LockedError,
    NoSuchItem,
)

if TYPE_CHECKING:
    from xandikos.web import CalendarCollection, ObjectResource


TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Autoescape — summaries/descriptions are user-controlled and inlined
# straight into HTML.
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
    autoescape=jinja2.select_autoescape(["html"]),
    enable_async=True,
)


# ---------------------------------------------------------------------------
# Date helpers


def _today() -> date:
    return date.today()


def _parse_month(s: str | None) -> tuple[int, int]:
    """Parse a ``YYYY-MM`` query string, falling back to the current month."""
    if s:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})", s.strip())
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            if 1 <= month <= 12 and 1 <= year <= 9999:
                return year, month
    t = _today()
    return t.year, t.month


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _month_grid(year: int, month: int) -> list[list[date]]:
    """Six-week grid of dates that visually contains the month.

    Weeks start on Monday. The first row may include trailing days from
    the previous month; the last row may include leading days from the
    next month.
    """
    cal = stdcalendar.Calendar(firstweekday=0)
    return list(cal.monthdatescalendar(year, month))


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, (idx % 12) + 1


def _as_date(value: date | datetime) -> date:
    """Reduce a datetime to a date, leaving plain dates alone."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _local_naive(dt: date | datetime) -> datetime | date:
    """Convert tz-aware datetimes to naive local time for the form."""
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.astimezone().replace(tzinfo=None)
        return dt
    return dt


def _format_dtlocal(dt: datetime) -> str:
    """``datetime-local`` form input expects ``YYYY-MM-DDTHH:MM``."""
    return dt.strftime("%Y-%m-%dT%H:%M")


def _format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _occurrences_on(comp, day: date) -> list[tuple[datetime | date, datetime | date]]:
    """Return ``(start, end)`` tuples for the parts of ``comp`` on ``day``.

    Returns an empty list if the component doesn't touch ``day``.
    """
    start = comp.get("DTSTART")
    end = comp.get("DTEND") or comp.get("DUE")
    if start is None:
        return []
    s = start.dt
    e = end.dt if end is not None else s
    if isinstance(s, datetime):
        s = _local_naive(s)
    if isinstance(e, datetime):
        e = _local_naive(e)
    s_date = _as_date(s)
    e_date = _as_date(e)
    # DTEND is exclusive for all-day events per RFC 5545 §3.8.2.2.
    if not isinstance(s, datetime) and e_date > s_date:
        e_date -= timedelta(days=1)
    if s_date <= day <= e_date:
        return [(s, e)]
    return []


# ---------------------------------------------------------------------------
# Collection -> events index


def _iter_components(collection: CalendarCollection):
    """Yield ``(name, etag, component)`` for every VEVENT and VTODO."""
    for name, content_type, etag in collection.store.iter_with_etag():
        if content_type != "text/calendar":
            continue
        try:
            file = collection.store.get_file(name, content_type, etag)
        except (KeyError, InvalidFileContents):
            continue
        try:
            cal = file.calendar
        except (InvalidFileContents, ValueError):
            continue
        if cal is None:
            continue
        for comp in cal.subcomponents:
            if comp.name in ("VEVENT", "VTODO"):
                yield name, etag, comp


def collect_occurrences(
    collection: CalendarCollection, start: date, end: date
) -> list[dict[str, Any]]:
    """Return one dict per occurrence overlapping ``[start, end]``.

    Recurring events are expanded via ``expand_calendar_rrule``; one
    entry is produced per expanded instance. Each dict contains:
    ``name``, ``etag``, ``kind`` (``event``/``todo``), ``summary``,
    ``start_date``, ``end_date``, ``start_time``, ``all_day``,
    ``status`` (todos), ``href``.
    """
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)

    out: list[dict[str, Any]] = []
    for name, content_type, etag in collection.store.iter_with_etag():
        if content_type != "text/calendar":
            continue
        try:
            file = collection.store.get_file(name, content_type, etag)
        except (KeyError, InvalidFileContents):
            continue
        try:
            src_cal = file.calendar
        except (InvalidFileContents, ValueError):
            continue
        if src_cal is None:
            continue
        try:
            expanded = expand_calendar_rrule(src_cal, start_dt, end_dt)
        except (ValueError, TypeError, AttributeError):
            # Malformed RRULE or unparseable component — fall back to
            # the original (unexpanded) calendar so the user still sees
            # the master instance.
            expanded = src_cal

        for comp in expanded.subcomponents:
            if comp.name not in ("VEVENT", "VTODO"):
                continue
            dtstart = comp.get("DTSTART")
            dtend = comp.get("DTEND") or comp.get("DUE")
            if dtstart is None:
                # VTODO without DUE — pin it to today so it shows up
                # somewhere if it overlaps the window.
                if comp.name == "VTODO" and start <= _today() <= end:
                    out.append(_summarize(name, etag, comp, _today(), None))
                continue
            s = _local_naive(dtstart.dt)
            e = _local_naive(dtend.dt) if dtend is not None else s
            s_d = _as_date(s)
            e_d = _as_date(e)
            all_day = not isinstance(s, datetime)
            # DTEND is exclusive for all-day events.
            if all_day and e_d > s_d:
                e_d -= timedelta(days=1)
            # Walk every day in [s_d, e_d] that falls inside the
            # requested window — multi-day events appear in each cell.
            day = max(s_d, start)
            last = min(e_d, end)
            while day <= last:
                out.append(
                    _summarize(name, etag, comp, day, s if not all_day else None)
                )
                day += timedelta(days=1)
    return out


def _summarize(
    name: str, etag: str, comp, day: date, start_time: datetime | date | None
) -> dict[str, Any]:
    return {
        "name": name,
        "etag": etag,
        "kind": "todo" if comp.name == "VTODO" else "event",
        "summary": str(comp.get("SUMMARY", "")),
        "date": day,
        "start_time": _format_time(start_time)
        if isinstance(start_time, datetime)
        else None,
        "all_day": not isinstance(start_time, datetime),
        "status": str(comp.get("STATUS", "")).upper(),
        "location": str(comp.get("LOCATION", "")),
    }


# ---------------------------------------------------------------------------
# Single-component <-> form helpers


def _read_dtlocal(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M")
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None


def component_to_form(comp) -> dict[str, Any]:
    """Pull the fields the edit form knows into a dict.

    Times come back as naive local datetimes (tz-aware inputs are
    converted) so the ``datetime-local`` form control can round-trip
    them without further conversion.
    """
    kind = "todo" if comp.name == "VTODO" else "event"
    dtstart = comp.get("DTSTART")
    dtend = comp.get("DTEND") or comp.get("DUE")

    all_day = False
    start_date = ""
    end_date = ""
    start_dt = ""
    end_dt = ""
    if dtstart is not None:
        s = _local_naive(dtstart.dt)
        if isinstance(s, datetime):
            start_dt = _format_dtlocal(s)
            start_date = s.date().isoformat()
        else:
            all_day = True
            start_date = s.isoformat()
    if dtend is not None:
        e = _local_naive(dtend.dt)
        if isinstance(e, datetime):
            end_dt = _format_dtlocal(e)
            end_date = e.date().isoformat()
        else:
            # All-day DTEND is exclusive; subtract a day so the form
            # shows the user-visible last day.
            shown = e - timedelta(days=1) if e > _as_date(s) else e
            end_date = shown.isoformat()

    return {
        "kind": kind,
        "summary": str(comp.get("SUMMARY", "")),
        "location": str(comp.get("LOCATION", "")),
        "description": str(comp.get("DESCRIPTION", "")),
        "all_day": all_day,
        "start_date": start_date,
        "end_date": end_date,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "status": str(comp.get("STATUS", "")).upper(),
        "rrule": str(comp.get("RRULE", "")),
        "has_attendees": "ATTENDEE" in comp,
        "uid": str(comp.get("UID", "")),
    }


def _clear_dt_props(comp) -> None:
    for key in ("DTSTART", "DTEND", "DUE"):
        if key in comp:
            del comp[key]


def _apply_form(comp, form: dict[str, str]) -> None:
    """Mutate ``comp`` in place from form fields.

    Only the fields the form owns are touched — RRULE, EXDATE,
    RECURRENCE-ID, ORGANIZER, ATTENDEE, custom X- properties, etc.
    are preserved.
    """
    summary = (form.get("summary") or "").strip()
    location = (form.get("location") or "").strip()
    description = (form.get("description") or "").strip()

    for key, value in (
        ("SUMMARY", summary),
        ("LOCATION", location),
        ("DESCRIPTION", description),
    ):
        if key in comp:
            del comp[key]
        if value:
            comp.add(key.lower(), value)

    all_day = form.get("all_day") == "1"
    _clear_dt_props(comp)

    if comp.name == "VTODO":
        # Tasks use DUE instead of DTEND/DTSTART; DTSTART is optional.
        if all_day:
            d = _parse_date(form.get("end_date") or form.get("start_date"))
            if d:
                comp.add("due", d)
        else:
            dt = _read_dtlocal(form.get("end_dt"))
            if dt:
                comp.add("due", dt)
        status = (form.get("status") or "").strip().upper()
        if "STATUS" in comp:
            del comp[key]
        if status in ("NEEDS-ACTION", "IN-PROCESS", "COMPLETED", "CANCELLED"):
            comp.add("status", status)
            if status == "COMPLETED" and "COMPLETED" not in comp:
                comp.add("completed", datetime.now(timezone.utc))
            elif status != "COMPLETED" and "COMPLETED" in comp:
                del comp["COMPLETED"]
        return

    # VEVENT
    if all_day:
        s = _parse_date(form.get("start_date"))
        e = _parse_date(form.get("end_date")) or s
        if s is None:
            return
        comp.add("dtstart", s)
        if e:
            # RFC 5545: DTEND for DATE is exclusive — store as last+1.
            comp.add("dtend", e + timedelta(days=1))
    else:
        s = _read_dtlocal(form.get("start_dt"))
        e = _read_dtlocal(form.get("end_dt")) or s
        if s is None:
            return
        comp.add("dtstart", s)
        if e:
            comp.add("dtend", e)


def new_calendar(comp) -> ICalendar:
    cal = ICalendar()
    cal.add("prodid", f"-//Xandikos//{xandikos_version}//EN")
    cal.add("version", "2.0")
    cal.add_component(comp)
    return cal


def build_new_component(form: dict[str, str]) -> ICalendar:
    """Build a fresh VCALENDAR with a single VEVENT or VTODO."""
    kind = (form.get("kind") or "event").lower()
    comp: IEvent | ITodo
    if kind == "todo":
        comp = ITodo()
    else:
        comp = IEvent()
    uid = (form.get("uid") or "").strip() or str(uuid.uuid4())
    comp.add("uid", uid)
    comp.add("dtstamp", datetime.now(timezone.utc))
    _apply_form(comp, form)
    return new_calendar(comp)


def update_calendar(existing_cal: ICalendar, form: dict[str, str]) -> ICalendar:
    """Apply form changes to the master VEVENT/VTODO of ``existing_cal``.

    Picks the first non-RECURRENCE-ID VEVENT/VTODO as the master.
    Other components (timezones, recurrence overrides, etc.) are kept
    intact.
    """
    master = None
    for comp in existing_cal.subcomponents:
        if comp.name in ("VEVENT", "VTODO") and "RECURRENCE-ID" not in comp:
            master = comp
            break
    if master is None:
        # Nothing recognisable to edit — replace with a fresh component.
        return build_new_component(form)
    _apply_form(master, form)
    # Bump DTSTAMP so other clients notice the change.
    if "DTSTAMP" in master:
        del master["DTSTAMP"]
    master.add("dtstamp", datetime.now(timezone.utc))
    if "LAST-MODIFIED" in master:
        del master["LAST-MODIFIED"]
    master.add("last-modified", datetime.now(timezone.utc))
    return existing_cal


# ---------------------------------------------------------------------------
# Rendering


async def _render_template(template_name: str, **kwargs):
    template = _jinja_env.get_template(template_name)
    body = await template.render_async(
        version=xandikos_version,
        urljoin=urllib.parse.urljoin,
        quote=urllib.parse.quote,
        today=_today(),
        **kwargs,
    )
    body_encoded = body.encode("utf-8")
    return (
        [body_encoded],
        len(body_encoded),
        None,
        "text/html; encoding=utf-8",
        ["en-UK"],
    )


def _self_url_normalised(self_url: str) -> tuple[str, str]:
    """Return ``(collection_url, query_string)`` from a self_url string.

    Path slashes are collapsed (see webcontacts._post_target_url for
    the reverse-proxy rationale). The collection URL ends with ``/``.
    """
    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    if not clean.endswith("/"):
        clean += "/"
    # If self_url pointed at a child URL (event, +day/..., +new), the
    # collection URL is its parent. Callers pass either the collection
    # URL itself or its child; we don't know which here — leave path
    # untouched and let the caller adjust as needed.
    return (
        urllib.parse.urlunsplit(parsed._replace(path=clean, query="", fragment="")),
        parsed.query,
    )


async def render_month(
    collection: CalendarCollection,
    self_url: str,
    accepted_content_types,
    accepted_content_languages,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render the month grid for the calendar."""
    webdav.pick_content_types(accepted_content_types, ["text/html"])
    collection_url, query = _self_url_normalised(self_url)

    params = urllib.parse.parse_qs(query)
    year, month = _parse_month((params.get("month") or [""])[0])

    grid = _month_grid(year, month)
    first_visible = grid[0][0]
    last_visible = grid[-1][-1]
    occurrences = collect_occurrences(collection, first_visible, last_visible)

    by_day: dict[date, list[dict[str, Any]]] = {}
    for occ in occurrences:
        by_day.setdefault(occ["date"], []).append(occ)
    for events in by_day.values():
        events.sort(key=lambda e: (e["all_day"] is False, e["start_time"] or ""))

    prev_year, prev_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, +1)

    return await _render_template(
        "calendar_month.html",
        collection=collection,
        collection_url=collection_url,
        year=year,
        month=month,
        month_name=stdcalendar.month_name[month],
        grid=grid,
        by_day=by_day,
        prev_url=f"{collection_url}?month={prev_year:04d}-{prev_month:02d}",
        next_url=f"{collection_url}?month={next_year:04d}-{next_month:02d}",
        today_url=collection_url,
        weekday_names=[stdcalendar.day_abbr[i] for i in range(7)],
    )


async def render_day(
    collection: CalendarCollection,
    self_url: str,
    day: date,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render the all-day list for a single date."""
    collection_url, _ = _self_url_normalised(self_url)
    # self_url is the +day/... URL; the collection URL is two levels up.
    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    parts = clean.rstrip("/").split("/")
    # drop "+day/YYYY-MM-DD"
    parts = parts[:-2]
    coll_path = "/".join(parts) + "/"
    collection_url = urllib.parse.urlunsplit(
        parsed._replace(path=coll_path, query="", fragment="")
    )

    occurrences = [
        o for o in collect_occurrences(collection, day, day) if o["date"] == day
    ]
    occurrences.sort(key=lambda e: (e["all_day"] is False, e["start_time"] or ""))

    return await _render_template(
        "calendar_day.html",
        collection=collection,
        collection_url=collection_url,
        day=day,
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1),
        events=occurrences,
    )


async def maybe_render_event(
    resource: ObjectResource,
    self_url: str,
    accepted_content_types,
    accepted_content_languages,
):
    """Render an iCalendar resource as HTML if HTML was acceptable."""
    available = ["text/calendar", "text/html"]
    try:
        picked = webdav.pick_content_types(accepted_content_types, available)
    except webdav.NotAcceptableError:
        return None
    if "text/html" not in picked:
        return None

    file = await resource.get_file()
    if not isinstance(file, ICalendarFile):
        return None
    try:
        cal = file.calendar
    except (InvalidFileContents, ValueError):
        return None
    master = None
    for comp in cal.subcomponents:
        if comp.name in ("VEVENT", "VTODO") and "RECURRENCE-ID" not in comp:
            master = comp
            break
    if master is None:
        return None

    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    parent = clean.rsplit("/", 1)[0] + "/"
    collection_url = urllib.parse.urlunsplit(
        parsed._replace(path=parent, query="", fragment="")
    )

    return await _render_template(
        "event.html",
        resource=resource,
        component=component_to_form(master),
        name=resource.name,
        collection_url=collection_url,
    )


async def render_new_event_form(
    collection: CalendarCollection,
    collection_url: str,
    kind: str = "event",
    initial_date: date | None = None,
):
    """Empty edit form for creating a VEVENT or VTODO."""
    if initial_date is None:
        initial_date = _today()
    empty = {
        "kind": "todo" if kind == "todo" else "event",
        "summary": "",
        "location": "",
        "description": "",
        "all_day": False,
        "start_date": initial_date.isoformat(),
        "end_date": initial_date.isoformat(),
        "start_dt": _format_dtlocal(datetime.combine(initial_date, time(9, 0))),
        "end_dt": _format_dtlocal(datetime.combine(initial_date, time(10, 0))),
        "status": "NEEDS-ACTION",
        "rrule": "",
        "has_attendees": False,
        "uid": "",
    }
    return await _render_template(
        "event.html",
        resource=None,
        component=empty,
        name=None,
        collection_url=collection_url,
    )


# ---------------------------------------------------------------------------
# POST handling


def _parse_form(body: list[bytes], content_type: str) -> dict[str, str] | None:
    if content_type != "application/x-www-form-urlencoded":
        return None
    raw = b"".join(body).decode("utf-8", "replace")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {k: v[-1] for k, v in parsed.items()}


def _redirect(location: str, status: int = 303) -> webdav.Response:
    return webdav.Response(
        status=status, reason="See Other", headers=[("Location", location)]
    )


def _post_target_url(request) -> str:
    parsed = urllib.parse.urlsplit(str(request.url).split("?", 1)[0])
    new_path = re.sub(r"/+", "/", parsed.path) or "/"
    if not new_path.endswith("/"):
        new_path += "/"
    return urllib.parse.urlunsplit(
        parsed._replace(path=new_path, query="", fragment="")
    )


async def handle_post(
    collection: CalendarCollection,
    request,
    environ: dict,
    path: str,
    body: list[bytes],
    content_type: str,
) -> webdav.Response | None:
    """Handle a form-encoded post; return None for any other body."""
    form = _parse_form(body, content_type)
    if form is None:
        return None
    action = (form.get("action") or "").strip().lower()
    if action not in {"create", "update", "delete", "toggle_done"}:
        return None

    collection_url = _post_target_url(request)

    if action == "delete":
        name = (form.get("name") or "").strip()
        if not name or "/" in name:
            return webdav.Response(status=400, reason="Bad Request")
        try:
            collection.delete_member(
                name,
                remote_user=environ.get("REMOTE_USER"),
                requester=request.headers.get("User-Agent"),
            )
        except (KeyError, NoSuchItem):
            return webdav.Response(status=404, reason="Not Found")
        return _redirect(collection_url)

    if action == "toggle_done":
        # Quick-toggle on the day view: flip a VTODO between
        # NEEDS-ACTION and COMPLETED without opening the full form.
        name = (form.get("name") or "").strip()
        if not name or "/" in name:
            return webdav.Response(status=400, reason="Bad Request")
        try:
            existing = collection.get_member(name)
        except KeyError:
            return webdav.Response(status=404, reason="Not Found")
        file = await existing.get_file()
        if not isinstance(file, ICalendarFile):
            return webdav.Response(status=400, reason="Bad Request")
        cal = file.calendar
        for comp in cal.subcomponents:
            if comp.name == "VTODO" and "RECURRENCE-ID" not in comp:
                status_val = str(comp.get("STATUS", "")).upper()
                if status_val == "COMPLETED":
                    if "STATUS" in comp:
                        del comp["STATUS"]
                    if "COMPLETED" in comp:
                        del comp["COMPLETED"]
                    comp.add("status", "NEEDS-ACTION")
                else:
                    if "STATUS" in comp:
                        del comp["STATUS"]
                    if "COMPLETED" in comp:
                        del comp["COMPLETED"]
                    comp.add("status", "COMPLETED")
                    comp.add("completed", datetime.now(timezone.utc))
                if "DTSTAMP" in comp:
                    del comp["DTSTAMP"]
                comp.add("dtstamp", datetime.now(timezone.utc))
                break
        try:
            await existing.set_body(
                [cal.to_ical()],
                replace_etag=await existing.get_etag(),
                remote_user=environ.get("REMOTE_USER"),
                requester=request.headers.get("User-Agent"),
            )
        except LockedError:
            return webdav.Response(status=423, reason="Locked")
        back = (form.get("back_url") or "").strip()
        return _redirect(back or collection_url)

    if action == "create":
        cal_obj = build_new_component(form)
        # Build a deterministic file name from the UID we just minted.
        master_uid = ""
        for comp in cal_obj.subcomponents:
            if comp.name in ("VEVENT", "VTODO"):
                master_uid = str(comp.get("UID", ""))
                break
        if not master_uid:
            master_uid = str(uuid.uuid4())
        new_name = master_uid + ".ics"
        try:
            stored_name, _etag = await collection.create_member(
                new_name,
                [cal_obj.to_ical()],
                "text/calendar",
                remote_user=environ.get("REMOTE_USER"),
                requester=request.headers.get("User-Agent"),
            )
        except FileExistsError:
            return webdav.Response(status=409, reason="Conflict")
        except webdav.PreconditionFailure as e:
            return webdav.Response(
                status=400, reason="Bad Request", body=[e.description.encode("utf-8")]
            )
        except LockedError:
            return webdav.Response(status=423, reason="Locked")
        except DuplicateUidError:
            return webdav.Response(status=409, reason="Conflict")
        return _redirect(
            urllib.parse.urljoin(collection_url, urllib.parse.quote(stored_name))
        )

    # action == "update"
    name = (form.get("name") or "").strip()
    if not name or "/" in name:
        return webdav.Response(status=400, reason="Bad Request")
    try:
        existing = collection.get_member(name)
    except KeyError:
        return webdav.Response(status=404, reason="Not Found")
    file = await existing.get_file()
    if not isinstance(file, ICalendarFile):
        return webdav.Response(status=400, reason="Bad Request")
    cal = file.calendar
    updated = update_calendar(cal, form)
    try:
        await existing.set_body(
            [updated.to_ical()],
            replace_etag=await existing.get_etag(),
            remote_user=environ.get("REMOTE_USER"),
            requester=request.headers.get("User-Agent"),
        )
    except webdav.PreconditionFailure as e:
        return webdav.Response(
            status=400, reason="Bad Request", body=[e.description.encode("utf-8")]
        )
    except LockedError:
        return webdav.Response(status=423, reason="Locked")
    return _redirect(urllib.parse.urljoin(collection_url, urllib.parse.quote(name)))
