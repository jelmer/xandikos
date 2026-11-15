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

"""Browser-facing web views of collections."""

import re
import urllib.parse

from .. import webdav


def parent_url(url: str) -> str | None:
    """Return the URL one path segment up, or None for the root.

    Repeated slashes, which some reverse proxies inject, are collapsed.
    """
    parsed = urllib.parse.urlsplit(url)
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path == "/":
        return None
    path = path.rstrip("/").rsplit("/", 1)[0] + "/"
    return urllib.parse.urlunsplit(parsed._replace(path=path, query="", fragment=""))


def wants_html(accepted_content_types, native_type: str | None = None) -> bool:
    """Check whether the client prefers HTML, i.e. is a browser.

    If ``native_type`` is given, HTML has to be preferred over it; a tie,
    e.g. for ``*/*`` or a missing Accept header, goes to ``native_type``
    so that DAV clients keep getting the raw resource.
    """
    available = ["text/html"]
    if native_type is not None:
        available.append(native_type)
    try:
        content_types = webdav.pick_content_types(accepted_content_types, available)
    except webdav.NotAcceptableError:
        return False
    return content_types == ["text/html"]


def parse_form(body: list[bytes], content_type: str) -> dict[str, str] | None:
    """Parse a form submission, or return None if the body is not one.

    Only the last value of a repeated field is kept.
    """
    if content_type != "application/x-www-form-urlencoded":
        return None
    raw = b"".join(body).decode("utf-8", "replace")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {k: v[-1] for k, v in parsed.items()}


def see_other(location: str) -> webdav.Response:
    return webdav.Response(
        status=303, reason="See Other", headers=[("Location", location)]
    )


def request_collection_url(request) -> str:
    """Return the URL a form was posted to, for use in a redirect.

    Repeated slashes are collapsed; with SCRIPT_NAME='/' the path would
    otherwise start with "//", which browsers treat as a host name.
    """
    parsed = urllib.parse.urlsplit(str(request.url))
    path = re.sub(r"/+", "/", parsed.path) or "/"
    if not path.endswith("/"):
        path += "/"
    return urllib.parse.urlunsplit(parsed._replace(path=path, query="", fragment=""))
