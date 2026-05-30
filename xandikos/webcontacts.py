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

"""Browser-facing view of CardDAV address books.

Renders address-book collections and individual vCard resources as
HTML, and processes form posts that create, update or delete contacts.

The integration points with :mod:`xandikos.web` are intentionally
narrow: ``render_addressbook`` and ``maybe_render_contact`` produce
the same 5-tuple as ``webdav.Resource.render``, and ``handle_post``
returns a ``webdav.Response`` when it recognises a form action (or
``None`` to let the default RFC 5995 add-member path run).
"""

from __future__ import annotations

import asyncio
import os
import re
import urllib.parse
import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import jinja2
import vobject

from xandikos import __version__ as xandikos_version
from xandikos import webdav
from xandikos.web import parent_url as _parent_url
from xandikos.store import (
    DuplicateUidError,
    InvalidFileContents,
    LockedError,
    NoSuchItem,
)
from xandikos.vcard import get_vcard_properties

if TYPE_CHECKING:
    from xandikos.web import AddressbookCollection, ObjectResource


TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# A separate environment with autoescape — these templates inject
# user-controlled strings (display names, contact fields) into HTML,
# so the default no-escape policy of the shared env is unsafe here.
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
    autoescape=jinja2.select_autoescape(["html"]),
    enable_async=True,
)


def _first_text(vcard, name: str) -> str:
    """Return the first value of ``name``, or ``''`` if absent."""
    props = get_vcard_properties(vcard, name)
    if not props:
        return ""
    value = props[0].value
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return "" if value is None else str(value)


def _typed_values(vcard, name: str) -> list[dict[str, str]]:
    """Return ``[{value, type}]`` for repeated typed props (EMAIL, TEL)."""
    result: list[dict[str, str]] = []
    for prop in get_vcard_properties(vcard, name):
        value = prop.value
        if value is None:
            continue
        if isinstance(value, list):
            text = ", ".join(str(v) for v in value if v)
        else:
            text = str(value)
        type_param = ""
        params = getattr(prop, "params", {})
        types = params.get("TYPE") if params else None
        if types:
            type_param = (
                str(types[0]).upper() if isinstance(types, list) else str(types).upper()
            )
        result.append({"value": text, "type": type_param})
    return result


def _photo_data_uri(vcard) -> str:
    """Return a usable ``src`` for the contact's PHOTO, or ``''``.

    Handles both inline photos (base64-encoded, possibly with a TYPE
    giving the image subtype) and photos given as a plain URI.
    """
    props = get_vcard_properties(vcard, "PHOTO")
    if not props:
        return ""
    prop = props[0]
    value = prop.value
    params = getattr(prop, "params", {}) or {}
    encoding = params.get("ENCODING")
    if encoding:
        encoding = (
            str(encoding[0]) if isinstance(encoding, list) else str(encoding)
        ).upper()
    # Inline, base64-encoded binary.
    if encoding in ("B", "BASE64") or isinstance(value, bytes):
        import base64

        if isinstance(value, bytes):
            b64 = base64.b64encode(value).decode("ascii")
        else:
            # vobject hands us the already-encoded text; strip whitespace.
            b64 = "".join(str(value).split())
        types = params.get("TYPE")
        subtype = ""
        if types:
            subtype = (str(types[0]) if isinstance(types, list) else str(types)).lower()
        mime = f"image/{subtype}" if subtype else "image/jpeg"
        return f"data:{mime};base64,{b64}"
    # Otherwise treat it as a URI (http(s) or an existing data: URI).
    text = str(value).strip()
    if text.startswith(("http://", "https://", "data:")):
        return text
    return ""


def _categories(vcard) -> list[str]:
    """Return the contact's CATEGORIES as a flat list of labels."""
    out: list[str] = []
    for prop in get_vcard_properties(vcard, "CATEGORIES"):
        value = prop.value
        if isinstance(value, list):
            out.extend(str(v).strip() for v in value if str(v).strip())
        elif value:
            out.extend(part.strip() for part in str(value).split(",") if part.strip())
    return out


def _initial(fn: str, fallback: str) -> str:
    """First letter (uppercased) of ``fn`` for A-Z grouping; '#' otherwise."""
    text = (fn or fallback or "").strip()
    if not text:
        return "#"
    ch = text[0].upper()
    return ch if ch.isalpha() else "#"


def contact_summary(vcard) -> dict[str, Any]:
    """Compact summary for the list view."""
    fn = _first_text(vcard, "FN")
    return {
        "fn": fn,
        "emails": [e["value"] for e in _typed_values(vcard, "EMAIL")],
        "tels": [t["value"] for t in _typed_values(vcard, "TEL")],
        "org": _first_text(vcard, "ORG"),
        "photo": _photo_data_uri(vcard),
        "categories": _categories(vcard),
        "initial": _initial(fn, ""),
    }


def contact_to_form(vcard) -> dict[str, Any]:
    """Pull every field the edit form knows about into a dict."""
    n_props = get_vcard_properties(vcard, "N")
    name_parts = {
        "family": "",
        "given": "",
        "additional": "",
        "prefix": "",
        "suffix": "",
    }
    if n_props:
        n_value = n_props[0].value
        for key in name_parts:
            val = getattr(n_value, key, "")
            if isinstance(val, list):
                val = " ".join(v for v in val if v)
            name_parts[key] = val or ""
    return {
        "fn": _first_text(vcard, "FN"),
        "n": name_parts,
        "emails": _typed_values(vcard, "EMAIL"),
        "tels": _typed_values(vcard, "TEL"),
        "org": _first_text(vcard, "ORG"),
        "title": _first_text(vcard, "TITLE"),
        "url": _first_text(vcard, "URL"),
        "note": _first_text(vcard, "NOTE"),
    }


def _collect_indexed(form: dict[str, str], prefix: str) -> list[dict[str, str]]:
    """Gather ``prefix_N`` / ``prefix_type_N`` pairs into ordered dicts.

    Entries whose value is empty after stripping are dropped — this is
    how the form signals "delete this row".
    """
    indexes: set[int] = set()
    value_prefix = prefix + "_"
    type_prefix = prefix + "_type_"
    for key in form:
        if key.startswith(type_prefix):
            tail = key[len(type_prefix) :]
        elif key.startswith(value_prefix):
            tail = key[len(value_prefix) :]
        else:
            continue
        try:
            indexes.add(int(tail))
        except ValueError:
            continue
    result: list[dict[str, str]] = []
    for i in sorted(indexes):
        value = (form.get(f"{prefix}_{i}", "") or "").strip()
        if not value:
            continue
        type_val = (form.get(f"{prefix}_type_{i}", "") or "").strip().upper()
        result.append({"value": value, "type": type_val})
    return result


def vcard_from_form(form: dict[str, str], uid: str | None = None) -> bytes:
    """Serialise a vCard 3.0 from edit-form fields.

    A UID is generated if one isn't supplied; FN falls back to the
    concatenated N parts (or the UID) so the result is always valid.
    """
    card = vobject.vCard()
    card.add("version").value = "3.0"
    if uid is None:
        uid = str(uuid.uuid4())
    card.add("uid").value = uid

    fn = (form.get("fn", "") or "").strip()
    family = (form.get("family_name", "") or "").strip()
    given = (form.get("given_name", "") or "").strip()
    additional = (form.get("additional_names", "") or "").strip()
    prefix = (form.get("prefix", "") or "").strip()
    suffix = (form.get("suffix", "") or "").strip()
    if not fn:
        fn = " ".join(p for p in (prefix, given, additional, family, suffix) if p)
    if not fn:
        fn = uid
    card.add("fn").value = fn

    n = card.add("n")
    n.value = vobject.vcard.Name(
        family=family,
        given=given,
        additional=additional,
        prefix=prefix,
        suffix=suffix,
    )

    for email in _collect_indexed(form, "email"):
        prop = card.add("email")
        prop.value = email["value"]
        if email["type"]:
            prop.type_param = email["type"]

    for tel in _collect_indexed(form, "tel"):
        prop = card.add("tel")
        prop.value = tel["value"]
        if tel["type"]:
            prop.type_param = tel["type"]

    for key in ("org", "title", "url", "note"):
        value = (form.get(key, "") or "").strip()
        if not value:
            continue
        prop = card.add(key)
        # ORG is structured: the first list element is the organisation
        # name, additional components are organisational units.
        prop.value = [value] if key == "org" else value

    return card.serialize().encode("utf-8")


async def _render_template(
    template_name: str, **kwargs
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    if "parent_url" not in kwargs and "self_url" in kwargs:
        kwargs["parent_url"] = _parent_url(kwargs["self_url"])
    template = _jinja_env.get_template(template_name)
    body = await template.render_async(
        version=xandikos_version,
        urljoin=urllib.parse.urljoin,
        quote=urllib.parse.quote,
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


def _load_card(file):
    """Best-effort parse — broken cards still appear in the list view."""
    try:
        return file.addressbook
    except (InvalidFileContents, ValueError, AttributeError):
        return None


def _iter_contacts(collection: AddressbookCollection):
    """Yield ``(name, summary, etag)`` for each vCard in the collection.

    vCards we can't parse get a placeholder summary so the user can
    still see and delete them.
    """

    def _placeholder(nm: str) -> dict[str, Any]:
        return {
            "fn": nm,
            "emails": [],
            "tels": [],
            "org": "",
            "photo": "",
            "categories": [],
            "initial": _initial(nm, nm),
        }

    for name, content_type, etag in collection.store.iter_with_etag():
        if content_type != "text/vcard":
            continue
        try:
            file = collection.store.get_file(name, content_type, etag)
        except (KeyError, InvalidFileContents):
            yield name, _placeholder(name), etag
            continue
        card = _load_card(file)
        if card is None:
            yield name, _placeholder(name), etag
        else:
            yield name, contact_summary(card), etag


def export_addressbook(
    collection,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Return all vCards in the addressbook as one downloadable file.

    The stored cards are concatenated verbatim so the whole addressbook
    can be saved as a single ``.vcf`` file.
    """
    chunks: list[bytes] = []
    for name, content_type, etag in collection.store.iter_with_etag():
        if content_type != "text/vcard":
            continue
        try:
            file = collection.store.get_file(name, content_type, etag)
            raw = b"".join(file.content)
        except (KeyError, InvalidFileContents):
            continue
        if not raw.endswith(b"\n"):
            raw += b"\r\n"
        chunks.append(raw)
    body = b"".join(chunks)
    return (
        [body],
        len(body),
        None,
        "text/vcard; charset=utf-8",
        ["en-UK"],
    )


async def render_addressbook(
    collection: AddressbookCollection,
    self_url: str,
    accepted_content_types,
    accepted_content_languages,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Render the address book as an HTML contact list.

    Falls through to the regular ``collection.html`` if the client
    only accepts something other than text/html.
    """
    webdav.pick_content_types(accepted_content_types, ["text/html"])
    query = urllib.parse.parse_qs(
        urllib.parse.urlsplit(self_url).query, keep_blank_values=True
    )
    if "export" in query:
        return await asyncio.to_thread(export_addressbook, collection)
    search = (query.get("q") or [""])[0].strip()
    search_lc = search.lower()

    def _gather():
        rows = sorted(
            _iter_contacts(collection),
            key=lambda item: (
                item[1]["initial"],
                (item[1]["fn"] or "").lower() or item[0].lower(),
            ),
        )
        if not search_lc:
            return rows
        matched = []
        for name, summary, etag in rows:
            haystack = " ".join(
                [summary["fn"] or name, summary["org"], *summary["emails"]]
            ).lower()
            if search_lc in haystack:
                matched.append((name, summary, etag))
        return matched

    contacts = await asyncio.to_thread(_gather)
    return await _render_template(
        "addressbook.html",
        collection=collection,
        contacts=contacts,
        self_url=self_url,
        search=search,
    )


async def maybe_render_contact(
    resource: ObjectResource,
    self_url: str,
    accepted_content_types,
    accepted_content_languages,
    flash: str | None = None,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]] | None:
    """Render a vCard as HTML if the client asked for HTML.

    Returns ``None`` when the client only accepts text/vcard — the
    caller (``ObjectResource.render``) then serves the raw vCard so
    CardDAV clients still work.
    """
    available = ["text/vcard", "text/html"]
    try:
        picked = webdav.pick_content_types(accepted_content_types, available)
    except webdav.NotAcceptableError:
        return None
    if "text/html" not in picked:
        return None

    file = await resource.get_file()
    card = _load_card(file)
    if card is None:
        # Don't pretend to render something we can't parse.
        return None

    # The collection URL is the parent of self_url; we need it so the
    # form action can POST back to the collection (PostMethod restricts
    # POSTs to collections only). The path is also collapsed to remove
    # any "//" runs that some reverse-proxy setups inject — see
    # _post_target_url for the rationale.
    parsed = urllib.parse.urlsplit(self_url)
    clean_path = re.sub(r"/+", "/", parsed.path) or "/"
    parent_path = clean_path.rsplit("/", 1)[0] + "/"
    collection_url = urllib.parse.urlunsplit(parsed._replace(path=parent_path))

    return await _render_template(
        "contact.html",
        resource=resource,
        contact=contact_to_form(card),
        self_url=self_url,
        collection_url=collection_url,
        parent_url=collection_url,
        name=resource.name,
        etag=resource.etag,
        flash=flash,
    )


async def render_new_contact_form(
    collection: AddressbookCollection,
    collection_url: str,
) -> tuple[Iterable[bytes], int, str | None, str, list[str]]:
    """Empty edit form for creating a new contact."""
    empty = {
        "fn": "",
        "n": {"family": "", "given": "", "additional": "", "prefix": "", "suffix": ""},
        "emails": [],
        "tels": [],
        "org": "",
        "title": "",
        "url": "",
        "note": "",
    }
    return await _render_template(
        "contact.html",
        resource=None,
        contact=empty,
        self_url=collection_url,
        collection_url=collection_url,
        parent_url=collection_url,
        name=None,
        etag=None,
        flash=None,
    )


def _parse_form(body: list[bytes], content_type: str) -> dict[str, str] | None:
    """Parse ``application/x-www-form-urlencoded`` body, or None."""
    if content_type != "application/x-www-form-urlencoded":
        return None
    raw = b"".join(body).decode("utf-8", "replace")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    # parse_qs returns lists; collapse to last value per key — repeated
    # fields use distinct indexed names (email_0, email_1, ...).
    return {k: v[-1] for k, v in parsed.items()}


def _redirect(location: str, status: int = 303) -> webdav.Response:
    return webdav.Response(
        status=status, reason="See Other", headers=[("Location", location)]
    )


def _post_target_url(request, environ: dict, path: str) -> str:
    """Absolute URL of the addressbook collection the form posted to.

    Built from the request's own URL with consecutive slashes in the
    path collapsed — reverse-proxy setups that supply
    ``SCRIPT_NAME='/'`` would otherwise produce a Location starting
    with ``//``, which browsers interpret as protocol-relative (the
    next path segment becomes the host). The trailing slash matters:
    the form posts to the collection, so that's where ``request.url``
    already points.
    """
    # request.url is a str under WSGI but a yarl.URL under aiohttp;
    # str() handles both.
    parsed = urllib.parse.urlsplit(str(request.url).split("?", 1)[0])
    new_path = re.sub(r"/+", "/", parsed.path) or "/"
    if not new_path.endswith("/"):
        new_path += "/"
    return urllib.parse.urlunsplit(
        parsed._replace(path=new_path, query="", fragment="")
    )


async def handle_post(
    collection: AddressbookCollection,
    request,
    environ: dict,
    path: str,
    body: list[bytes],
    content_type: str,
) -> webdav.Response | None:
    """Dispatch a form post against an address-book collection.

    Returns ``None`` for any request that isn't a recognised form
    submission, so the default RFC 5995 add-member path still runs
    for real CardDAV clients posting raw vCards.
    """
    form = _parse_form(body, content_type)
    if form is None:
        return None
    action = (form.get("action") or "").strip().lower()
    if action not in {"create", "update", "delete", "import"}:
        return None

    collection_url = _post_target_url(request, environ, path)

    if action == "import":
        # Import pasted vCard text: each card becomes its own resource.
        raw = (form.get("data") or "").strip()
        if not raw:
            return _redirect(collection_url)
        try:
            cards = list(vobject.readComponents(raw))
        except Exception:
            return webdav.Response(status=400, reason="Invalid vCard data")
        for card in cards:
            uid = ""
            if hasattr(card, "uid"):
                uid = str(card.uid.value or "").strip()
            if not uid:
                uid = str(uuid.uuid4())
            try:
                await collection.create_member(
                    uid + ".vcf",
                    [card.serialize().encode("utf-8")],
                    "text/vcard",
                    remote_user=environ.get("REMOTE_USER"),
                    requester=request.headers.get("User-Agent"),
                )
            except (FileExistsError, DuplicateUidError):
                continue
            except LockedError:
                return webdav.Response(status=423, reason="Locked")
        return _redirect(collection_url)

    if action == "delete":
        name = form.get("name", "").strip()
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

    if action == "create":
        new_name = (form.get("name") or "").strip()
        if not new_name:
            new_name = str(uuid.uuid4()) + ".vcf"
        if "/" in new_name:
            return webdav.Response(status=400, reason="Bad Request")
        uid = os.path.splitext(new_name)[0]
        data = vcard_from_form(form, uid=uid)
        try:
            stored_name, _etag = await collection.create_member(
                new_name,
                [data],
                "text/vcard",
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
    name = form.get("name", "").strip()
    if not name or "/" in name:
        return webdav.Response(status=400, reason="Bad Request")
    try:
        existing = collection.get_member(name)
    except KeyError:
        return webdav.Response(status=404, reason="Not Found")

    # Preserve the original UID so other clients keep matching the card.
    existing_uid: str | None = None
    try:
        existing_file = await existing.get_file()
        card = _load_card(existing_file)
        if card is not None:
            uid_props = get_vcard_properties(card, "UID")
            if uid_props:
                existing_uid = str(uid_props[0].value)
    except (KeyError, InvalidFileContents):
        pass

    data = vcard_from_form(form, uid=existing_uid)
    try:
        await existing.set_body(
            [data],
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
