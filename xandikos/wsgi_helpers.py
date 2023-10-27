# Xandikos
# Copyright (C) 2016-2020 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""WSGI wrapper for xandikos."""

import posixpath

from .web import WELLKNOWN_DAV_PATHS


class WellknownRedirector:
    """Redirect paths under .well-known/ to the appropriate paths."""

    def __init__(self, inner_app, dav_root) -> None:
        self._inner_app = inner_app
        self._dav_root = dav_root

    def __call__(self, environ, start_response):
        # See https://tools.ietf.org/html/rfc6764
        path = posixpath.normpath(environ["SCRIPT_NAME"] + environ["PATH_INFO"])
        if path in WELLKNOWN_DAV_PATHS:
            start_response("302 Found", [("Location", self._dav_root)])
            return []
        return self._inner_app(environ, start_response)
