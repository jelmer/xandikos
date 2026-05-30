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
list, all tasks (VTODOs) as a single task list, and individual
VEVENT/VTODO resources as edit forms. Form posts create, update or
delete events and tasks.

Mirrors the shape of :mod:`xandikos.webcontacts`: ``render_month``,
``render_day``, ``maybe_render_event`` and ``render_new_event_form``
return the 5-tuple expected by ``webdav.Resource.render``, and
``handle_post`` returns a ``webdav.Response`` when it recognises a
form action (or ``None`` to let the default RFC 5995 add-member path
run for real CalDAV clients).
"""

from __future__ import annotations

import asyncio
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
from icalendar import Journal as IJournal
from icalendar import Todo as ITodo

from xandikos import __version__ as xandikos_version
from xandikos import webdav
from xandikos.icalendar import ICalendarFile, expand_calendar_rrule
from xandikos.web import parent_url as _parent_url
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
            due = comp.get("DUE")
            dtend = comp.get("DTEND") or due
            if dtstart is None:
                # A VTODO may carry a DUE without a DTSTART; anchor it to
                # the due date so it lands on the day it's due. Only when
                # there's neither do we pin it to today, so an undated
                # task still shows up somewhere in the window.
                if comp.name == "VTODO" and due is not None:
                    anchor = _local_naive(due.dt)
                    anchor_date = _as_date(anchor)
                    if start <= anchor_date <= end:
                        out.append(
                            _summarize(
                                name,
                                etag,
                                comp,
                                anchor_date,
                                anchor if isinstance(anchor, datetime) else None,
                            )
                        )
                elif comp.name == "VTODO" and start <= _today() <= end:
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

    if comp.name == "VJOURNAL":
        # Journal entries are dated notes: a single DATE-valued DTSTART,
        # plus the SUMMARY/DESCRIPTION already applied above.
        d = _parse_date(form.get("start_date"))
        if d:
            comp.add("dtstart", d)
        return

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
    comp: IEvent | ITodo | IJournal
    if kind == "todo":
        comp = ITodo()
    elif kind == "journal":
        comp = IJournal()
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
        if comp.name in ("VEVENT", "VTODO", "VJOURNAL") and "RECURRENCE-ID" not in comp:
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


async def _render_template(template_name: str, **kwargs):
    if "parent_url" not in kwargs and "self_url" in kwargs:
        kwargs["parent_url"] = _parent_url(kwargs["self_url"])
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


def _calendar_meta(collection) -> tuple[str | None, str | None]:
    """Return ``(color, description)`` for a calendar, each or both None."""

    def _safe(getter):
        try:
            value = getter()
        except (KeyError, AttributeError):
            return None
        return value or None

    return _safe(collection.get_calendar_color), _safe(
        collection.get_calendar_description
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

    color, description = _calendar_meta(collection)

    return await _render_template(
        "calendar_month.html",
        collection=collection,
        collection_url=collection_url,
        parent_url=_parent_url(collection_url),
        year=year,
        month=month,
        month_name=stdcalendar.month_name[month],
        grid=grid,
        by_day=by_day,
        prev_url=f"{collection_url}?month={prev_year:04d}-{prev_month:02d}",
        next_url=f"{collection_url}?month={next_year:04d}-{next_month:02d}",
        today_url=collection_url,
        weekday_names=[stdcalendar.day_abbr[i] for i in range(7)],
        color=color,
        description=description,
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
        parent_url=collection_url,
        day=day,
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1),
        events=occurrences,
    )


def _week_start(day: date) -> date:
    """Return the Monday of the week containing ``day``."""
    return day - timedelta(days=day.weekday())


async def render_week(
    collection: CalendarCollection,
    self_url: str,
    anchor: date,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render a Monday-to-Sunday week containing ``anchor``."""
    # self_url is the +week/... URL; the collection URL is two levels up.
    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    parts = clean.rstrip("/").split("/")
    parts = parts[:-2]
    coll_path = "/".join(parts) + "/"
    collection_url = urllib.parse.urlunsplit(
        parsed._replace(path=coll_path, query="", fragment="")
    )

    start = _week_start(anchor)
    end = start + timedelta(days=6)
    days = [start + timedelta(days=i) for i in range(7)]

    occurrences = collect_occurrences(collection, start, end)
    by_day: dict[date, list[dict[str, Any]]] = {}
    for occ in occurrences:
        by_day.setdefault(occ["date"], []).append(occ)
    for events in by_day.values():
        events.sort(key=lambda e: (e["all_day"] is False, e["start_time"] or ""))

    return await _render_template(
        "calendar_week.html",
        collection=collection,
        collection_url=collection_url,
        parent_url=collection_url,
        days=days,
        by_day=by_day,
        start=start,
        end=end,
        prev_day=start - timedelta(days=7),
        next_day=start + timedelta(days=7),
    )


_TODO_STATUS_ORDER = {
    "IN-PROCESS": 0,
    "NEEDS-ACTION": 1,
    "": 1,
    "COMPLETED": 2,
    "CANCELLED": 3,
}


def _task_summary(name: str, etag: str, comp) -> dict[str, Any]:
    """Summarise a VTODO for the task-list view.

    ``due`` is the local-naive DUE value (or ``None``); ``due_str`` is a
    short rendering for display; ``done`` is True for completed tasks.
    """
    due_prop = comp.get("DUE") or comp.get("DTSTART")
    due_value: date | datetime | None = None
    if due_prop is not None:
        due_value = _local_naive(due_prop.dt)
    if isinstance(due_value, datetime):
        due_str = due_value.strftime("%Y-%m-%d %H:%M")
        due_sort = due_value
    elif isinstance(due_value, date):
        due_str = due_value.isoformat()
        due_sort = datetime.combine(due_value, time.min)
    else:
        due_str = ""
        due_sort = None
    status = str(comp.get("STATUS", "")).upper()
    return {
        "name": name,
        "etag": etag,
        "summary": str(comp.get("SUMMARY", "")),
        "status": status,
        "done": status in ("COMPLETED", "CANCELLED"),
        "due_str": due_str,
        "due_sort": due_sort,
        "location": str(comp.get("LOCATION", "")),
    }


def collect_tasks(collection: CalendarCollection) -> list[dict[str, Any]]:
    """Return one summary dict per master VTODO in the collection.

    Per-instance overrides (RECURRENCE-ID) are skipped so each task
    appears once. Open tasks sort before done ones; within each group,
    tasks with a due date sort earliest-first and undated tasks trail.
    """
    tasks: list[dict[str, Any]] = []
    for name, etag, comp in _iter_components(collection):
        if comp.name != "VTODO" or "RECURRENCE-ID" in comp:
            continue
        tasks.append(_task_summary(name, etag, comp))

    def sort_key(t: dict[str, Any]):
        # Open before done; then by status priority; then by due date
        # (undated last); then summary for stability.
        return (
            t["done"],
            _TODO_STATUS_ORDER.get(t["status"], 1),
            t["due_sort"] is None,
            t["due_sort"] or datetime.max,
            t["summary"].lower(),
        )

    tasks.sort(key=sort_key)
    return tasks


async def render_tasks(
    collection: CalendarCollection,
    self_url: str,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render every VTODO in the calendar as a single task list."""
    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    # self_url is the +tasks URL; the collection URL is one level up.
    parts = clean.rstrip("/").split("/")
    parts = parts[:-1]
    coll_path = "/".join(parts) + "/"
    collection_url = urllib.parse.urlunsplit(
        parsed._replace(path=coll_path, query="", fragment="")
    )
    tasks_url = urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))
    if not tasks_url.endswith("/"):
        tasks_url += "/"

    tasks = await asyncio.to_thread(collect_tasks, collection)
    open_tasks = [t for t in tasks if not t["done"]]
    done_tasks = [t for t in tasks if t["done"]]

    return await _render_template(
        "tasks.html",
        collection=collection,
        collection_url=collection_url,
        tasks_url=tasks_url,
        parent_url=collection_url,
        open_tasks=open_tasks,
        done_tasks=done_tasks,
        total=len(tasks),
    )


def _iter_principal_calendars(principal):
    """Yield ``(home_name, cal_name, resource)`` for the principal's calendars.

    A principal's direct children are collection *homes*; the actual
    calendars are their members. A member is treated as a calendar when
    it exposes a ``store`` with ``iter_with_etag`` (what
    :func:`collect_occurrences` needs) — this avoids importing CalDAV
    resource-type constants here and tolerates odd collections.
    """
    try:
        homes = list(principal.subcollections())
    except (KeyError, AttributeError):
        return
    for home_name, home in homes:
        members = getattr(home, "members", None)
        if members is None:
            continue
        try:
            entries = list(members())
        except (KeyError, AttributeError, OSError):
            continue
        for cal_name, resource in entries:
            store = getattr(resource, "store", None)
            if store is None or not hasattr(store, "iter_with_etag"):
                continue
            yield home_name, cal_name, resource


def collect_principal_agenda(principal, days: int = 7) -> list[dict[str, Any]]:
    """Return upcoming occurrences across all the principal's calendars.

    Walks every calendar reachable from ``principal``, collects the
    occurrences over ``[today, today + days]`` and returns them sorted by
    date and time. Each entry is a ``collect_occurrences`` dict augmented
    with ``home`` (home name), ``calendar`` (calendar name) and ``color``.
    """
    today = _today()
    end = today + timedelta(days=days)
    out: list[dict[str, Any]] = []
    for home_name, cal_name, resource in _iter_principal_calendars(principal):
        try:
            occurrences = collect_occurrences(resource, today, end)
        except (KeyError, InvalidFileContents, ValueError):
            continue
        color = ""
        try:
            color = resource.get_calendar_color() or ""
        except (KeyError, AttributeError):
            pass
        for occ in occurrences:
            occ = dict(occ)
            occ["home"] = home_name
            occ["calendar"] = cal_name
            occ["color"] = color
            out.append(occ)
    out.sort(key=lambda e: (e["date"], e["all_day"] is False, e["start_time"] or ""))
    return out


async def render_subscription(
    collection,
    self_url: str,
    days_ahead: int = 30,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render a read-only overview of a calendar subscription.

    Shows the feed's source URL, colour and refresh rate, plus the
    cached events falling within the next ``days_ahead`` days. The
    subscription mirrors an external feed, so this view offers no
    editing controls.
    """
    collection_url, _ = _self_url_normalised(self_url)

    today = _today()
    occurrences = await asyncio.to_thread(
        collect_occurrences, collection, today, today + timedelta(days=days_ahead)
    )
    occurrences.sort(
        key=lambda e: (e["date"], e["all_day"] is False, e["start_time"] or "")
    )

    def _safe(getter):
        try:
            value = getter()
        except (KeyError, AttributeError):
            return None
        return value or None

    source_url = _safe(collection.get_source_url)
    color = _safe(collection.get_calendar_color)
    description = _safe(collection.get_calendar_description)
    refreshrate = _safe(collection.get_refreshrate)

    return await _render_template(
        "subscription.html",
        collection=collection,
        collection_url=collection_url,
        parent_url=_parent_url(collection_url),
        source_url=source_url,
        color=color,
        description=description,
        refreshrate=refreshrate,
        events=occurrences,
        days_ahead=days_ahead,
    )


def _format_period(period) -> dict[str, str]:
    """Turn an icalendar vPeriod into display strings for the outbox view."""
    start, end = period.dt
    fbtype = ""
    params = getattr(period, "params", None)
    if params:
        fbtype = str(params.get("FBTYPE", "") or "")
    return {
        "start": _local_naive(start).strftime("%Y-%m-%d %H:%M")
        if isinstance(start, datetime)
        else str(start),
        "end": _local_naive(end).strftime("%Y-%m-%d %H:%M")
        if isinstance(end, datetime)
        else str(end),
        "fbtype": fbtype or "BUSY",
    }


async def render_outbox(
    collection,
    self_url: str,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render the schedule outbox as a free/busy lookup form.

    A bare GET shows an empty form. When the query string carries
    ``attendee``, ``start`` and ``end``, the attendee's busy periods over
    that range are looked up via :meth:`ScheduleOutbox.get_attendee_busy_periods`
    and listed.
    """
    collection_url, query_string = _self_url_normalised(self_url)
    params = urllib.parse.parse_qs(query_string)
    attendee = (params.get("attendee") or [""])[0].strip()
    start_date = _parse_date((params.get("start") or [""])[0])
    end_date = _parse_date((params.get("end") or [""])[0])

    periods: list[dict[str, str]] | None = None
    error = ""
    submitted = bool(attendee or start_date or end_date)
    if submitted:
        if not attendee:
            error = "Enter an attendee address."
        elif start_date is None or end_date is None:
            error = "Enter a valid start and end date."
        elif end_date < start_date:
            error = "The end date must not be before the start date."
        else:
            addr = (
                attendee
                if "@" not in attendee or ":" in attendee
                else ("mailto:" + attendee)
            )
            start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
            raw = await collection.get_attendee_busy_periods(addr, start_dt, end_dt)
            if raw is None:
                error = (
                    "This server has no authority over that attendee, so no "
                    "free/busy information is available."
                )
            else:
                periods = [_format_period(p) for p in raw]

    return await _render_template(
        "outbox.html",
        collection=collection,
        collection_url=collection_url,
        parent_url=_parent_url(collection_url),
        attendee=attendee,
        start=(params.get("start") or [""])[0],
        end=(params.get("end") or [""])[0],
        periods=periods,
        error=error,
        submitted=submitted,
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
        if comp.name in ("VEVENT", "VTODO", "VJOURNAL") and "RECURRENCE-ID" not in comp:
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

    # Journals are dated notes; they use a simpler dedicated form rather
    # than the event/task editor.
    if master.name == "VJOURNAL":
        return await _render_template(
            "journal.html",
            resource=resource,
            journal=_journal_to_form(master),
            name=resource.name,
            collection_url=collection_url,
            parent_url=collection_url,
        )

    return await _render_template(
        "event.html",
        resource=resource,
        component=component_to_form(master),
        name=resource.name,
        collection_url=collection_url,
        parent_url=collection_url,
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
        parent_url=collection_url,
    )


async def render_settings_form(
    collection: CalendarCollection,
    self_url: str,
):
    """Render the calendar settings form (name, colour, description)."""
    # self_url is the +settings URL; the collection URL is its parent.
    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    parts = clean.rstrip("/").split("/")[:-1]
    coll_path = "/".join(parts) + "/"
    collection_url = urllib.parse.urlunsplit(
        parsed._replace(path=coll_path, query="", fragment="")
    )

    color, description = _calendar_meta(collection)
    try:
        displayname = collection.get_displayname()
    except KeyError:
        displayname = ""

    return await _render_template(
        "calendar_settings.html",
        collection=collection,
        collection_url=collection_url,
        parent_url=collection_url,
        displayname=displayname or "",
        color=color or "",
        description=description or "",
    )


def _journal_to_form(comp) -> dict[str, Any]:
    """Pull a VJOURNAL's fields into the journal form dict."""
    dtstart = comp.get("DTSTART")
    entry_date = ""
    if dtstart is not None:
        entry_date = _as_date(_local_naive(dtstart.dt)).isoformat()
    return {
        "summary": str(comp.get("SUMMARY", "")),
        "description": str(comp.get("DESCRIPTION", "")),
        "start_date": entry_date,
        "uid": str(comp.get("UID", "")),
    }


def _journal_summary(name: str, etag: str, comp) -> dict[str, Any]:
    """Summarise a VJOURNAL for the journal list."""
    dtstart = comp.get("DTSTART")
    entry_date: date | None = None
    if dtstart is not None:
        entry_date = _as_date(_local_naive(dtstart.dt))
    description = str(comp.get("DESCRIPTION", ""))
    # A short single-line preview of the body for the list view.
    preview = " ".join(description.split())
    if len(preview) > 140:
        preview = preview[:139].rstrip() + "…"
    return {
        "name": name,
        "etag": etag,
        "summary": str(comp.get("SUMMARY", "")),
        "date": entry_date,
        "date_str": entry_date.isoformat() if entry_date else "",
        "preview": preview,
    }


def collect_journals(collection: CalendarCollection) -> list[dict[str, Any]]:
    """Return one summary per master VJOURNAL, newest entry first."""
    journals: list[dict[str, Any]] = []
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
            if comp.name == "VJOURNAL" and "RECURRENCE-ID" not in comp:
                journals.append(_journal_summary(name, etag, comp))

    # Dated entries newest-first; undated ones trail at the bottom.
    journals.sort(
        key=lambda j: (j["date"] is None, j["date"] or date.min, j["summary"].lower()),
        reverse=False,
    )
    dated = [j for j in journals if j["date"] is not None]
    undated = [j for j in journals if j["date"] is None]
    dated.sort(key=lambda j: j["date"], reverse=True)
    return dated + undated


async def render_journals(
    collection: CalendarCollection,
    self_url: str,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render every VJOURNAL in the calendar as a list."""
    parsed = urllib.parse.urlsplit(self_url)
    clean = re.sub(r"/+", "/", parsed.path) or "/"
    # self_url is the +journal URL; the collection URL is one level up.
    parts = clean.rstrip("/").split("/")
    parts = parts[:-1]
    coll_path = "/".join(parts) + "/"
    collection_url = urllib.parse.urlunsplit(
        parsed._replace(path=coll_path, query="", fragment="")
    )

    journals = await asyncio.to_thread(collect_journals, collection)

    return await _render_template(
        "journals.html",
        collection=collection,
        collection_url=collection_url,
        parent_url=collection_url,
        journals=journals,
    )


async def render_new_journal_form(
    collection: CalendarCollection,
    collection_url: str,
    initial_date: date | None = None,
):
    """Empty edit form for creating a VJOURNAL."""
    if initial_date is None:
        initial_date = _today()
    empty = {
        "summary": "",
        "description": "",
        "start_date": initial_date.isoformat(),
        "uid": "",
    }
    return await _render_template(
        "journal.html",
        resource=None,
        journal=empty,
        name=None,
        collection_url=collection_url,
        parent_url=collection_url,
    )


_ITIP_METHODS = (
    "REQUEST",
    "REPLY",
    "CANCEL",
    "ADD",
    "REFRESH",
    "COUNTER",
    "DECLINECOUNTER",
)


def _itip_summary(name: str, etag: str, raw: bytes) -> dict[str, Any]:
    """Extract a one-row summary from an iTIP message body.

    Returns placeholder values for messages we can't parse so the user
    can still see and delete them in the inbox.
    """
    placeholder = {
        "name": name,
        "etag": etag,
        "method": "",
        "method_class": "other",
        "summary": name,
        "when": "",
        "organizer": "",
    }
    try:
        cal = ICalendar.from_ical(raw.decode("utf-8", "replace"))
    except ValueError:
        return placeholder
    method = str(cal.get("METHOD", "")).upper()
    method_class = method.lower() if method in _ITIP_METHODS else "other"
    # Pick the most representative VEVENT/VTODO for the row. iTIP REQUESTs
    # often carry just one component — possibly a per-instance override
    # (RECURRENCE-ID), e.g. Google Calendar invites to a single occurrence
    # of a recurring meeting — so we don't insist on a master.
    candidates = [c for c in cal.subcomponents if c.name in ("VEVENT", "VTODO")]
    masters = [c for c in candidates if "RECURRENCE-ID" not in c]
    chosen = masters[0] if masters else (candidates[0] if candidates else None)
    summary = ""
    organizer = ""
    when_value: date | datetime | None = None
    if chosen is not None:
        summary = str(chosen.get("SUMMARY", ""))
        organizer = str(chosen.get("ORGANIZER", "")).removeprefix("mailto:")
        dtstart = chosen.get("DTSTART") or chosen.get("RECURRENCE-ID")
        if dtstart is not None:
            when_value = dtstart.dt
    when_str = ""
    if isinstance(when_value, datetime):
        when_str = _local_naive(when_value).strftime("%Y-%m-%d %H:%M")
    elif isinstance(when_value, date):
        when_str = when_value.isoformat()
    return {
        "name": name,
        "etag": etag,
        "method": method,
        "method_class": method_class,
        "summary": summary or name,
        "when": when_str,
        "organizer": organizer,
    }


async def render_inbox(
    collection,
    self_url: str,
    accepted_content_types,
    accepted_content_languages,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render a schedule-inbox as an HTML list of iTIP messages."""
    webdav.pick_content_types(accepted_content_types, ["text/html"])

    def _gather():
        store = collection.store
        rows = []
        for name, content_type, etag in store.iter_with_etag():
            if content_type != "text/calendar":
                continue
            try:
                raw = b"".join(store._get_raw(name, etag))
            except (KeyError, InvalidFileContents):
                continue
            rows.append(_itip_summary(name, etag, raw))
        # Newest-first on the rows that have a DTSTART; rows without one
        # (some REPLY/CANCEL flows) trail at the bottom.
        with_when = sorted(
            (r for r in rows if r["when"]), key=lambda r: r["when"], reverse=True
        )
        without = [r for r in rows if not r["when"]]
        return with_when + without

    messages = await asyncio.to_thread(_gather)

    try:
        default_calendar_url = collection.get_schedule_default_calendar_url()
    except (AttributeError, KeyError):
        default_calendar_url = None

    return await _render_template(
        "inbox.html",
        collection=collection,
        self_url=self_url,
        messages=messages,
        default_calendar_url=default_calendar_url,
    )


_INBOX_PARTSTATS = {
    "accept": "ACCEPTED",
    "tentative": "TENTATIVE",
    "decline": "DECLINED",
}


async def handle_inbox_post(
    collection,
    request,
    environ: dict,
    path: str,
    body: list[bytes],
    content_type: str,
) -> webdav.Response | None:
    """Handle a form-encoded post against a schedule inbox.

    Recognises ``accept``/``tentative``/``decline`` (REPLY back to the
    organiser, update the local copy's PARTSTAT, then drop the message)
    and ``delete`` (drop the message without replying — appropriate for
    REPLY/CANCEL flows that auto-processing already handled).
    """
    form = _parse_form(body, content_type)
    if form is None:
        return None
    action = (form.get("action") or "").strip().lower()
    if action not in {"delete", "accept", "tentative", "decline"}:
        return None
    name = (form.get("name") or "").strip()
    if not name or "/" in name:
        return webdav.Response(status=400, reason="Bad Request")

    if action == "delete":
        try:
            collection.delete_member(
                name,
                remote_user=environ.get("REMOTE_USER"),
                requester=request.headers.get("User-Agent"),
            )
        except (KeyError, NoSuchItem):
            return webdav.Response(status=404, reason="Not Found")
        return _redirect(_post_target_url(request))

    partstat = _INBOX_PARTSTATS[action]
    try:
        await collection.apply_attendee_action(name, partstat)
    except KeyError:
        return webdav.Response(status=404, reason="Not Found")
    except ValueError as exc:
        return webdav.Response(status=400, reason=str(exc) or "Bad Request")
    return _redirect(_post_target_url(request))


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
    if action not in {"create", "update", "delete", "toggle_done", "settings"}:
        return None

    collection_url = _post_target_url(request)

    if action == "settings":
        # Update the calendar's display name, colour and description from
        # the settings form. The store's set_color rejects empty values,
        # so an empty colour field is left untouched rather than cleared.
        #
        # Each write commits to the store, and set_displayname clears the
        # backend's open-store cache — so a collection instance reused
        # across writes ends up pointing at a stale store and the next
        # write fails. Re-resolve the collection from the backend before
        # each write so every mutation runs against a fresh store.
        backend = collection.backend
        # backend.get_resource expects an absolute path; collection.relpath
        # is stored without a leading slash.
        relpath = "/" + collection.relpath.lstrip("/")
        color = (form.get("color") or "").strip()
        if color:
            backend.get_resource(relpath).set_calendar_color(color)
        description = (form.get("description") or "").strip()
        backend.get_resource(relpath).set_calendar_description(description)
        name = (form.get("displayname") or "").strip()
        if name:
            backend.get_resource(relpath).set_displayname(name)
        return _redirect(collection_url)

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
        # Views that delete in place (e.g. the task list) pass back_url
        # so the user lands where they were rather than the month grid.
        back = (form.get("back_url") or "").strip()
        return _redirect(back or collection_url)

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
            if comp.name in ("VEVENT", "VTODO", "VJOURNAL"):
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
