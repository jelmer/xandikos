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

"""HTTP client for delivering WebDAV-Push messages.

Push-resource URLs are validated when a subscription is registered, but
that alone does not stop a push service from redirecting delivery to an
internal address, or from changing its DNS records afterwards. The
session returned by :func:`make_session` checks the resolved address of
every connection it makes and connects to exactly the address it
checked. It also does not follow redirects; neither RFC 8030 nor
WebDAV-Push defines them for push message delivery.

This module depends on ``requests`` (pulled in by ``pywebpush``), so it
is only imported when a push message is actually delivered.
"""

import socket

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util import connection

from .webdav_push import (
    NonPublicHostError,
    _allow_internal_push_resource,
    _resolve_public_host,
)


def _connect_public(conn: HTTPConnection) -> socket.socket:
    """Connect ``conn`` to its host, refusing internal addresses."""
    try:
        addrs = _resolve_public_host(conn._dns_host.strip("[]"))
    except NonPublicHostError as exc:
        raise NewConnectionError(conn, str(exc)) from exc
    last_error: OSError | None = None
    # Connect to the addresses that were checked rather than letting
    # create_connection resolve the name again.
    for addr in dict.fromkeys(addrs):
        try:
            return connection.create_connection(
                (str(addr), conn.port),
                conn.timeout,
                source_address=conn.source_address,
                socket_options=conn.socket_options,
            )
        except OSError as exc:
            last_error = exc
    raise NewConnectionError(
        conn, f"Failed to establish a new connection: {last_error}"
    ) from last_error


class _PublicHTTPConnection(HTTPConnection):
    def _new_conn(self) -> socket.socket:
        if _allow_internal_push_resource():
            return super()._new_conn()
        return _connect_public(self)


class _PublicHTTPSConnection(HTTPSConnection):
    def _new_conn(self) -> socket.socket:
        if _allow_internal_push_resource():
            return super()._new_conn()
        return _connect_public(self)


class _PublicHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _PublicHTTPConnection


class _PublicHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PublicHTTPSConnection


class _PublicAddressAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs) -> None:
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _PublicHTTPConnectionPool,
            "https": _PublicHTTPSConnectionPool,
        }


class _NoRedirectSession(requests.Session):
    def get_redirect_target(self, resp: requests.Response) -> None:
        return None


def make_session() -> requests.Session:
    """Create a session that only connects to public addresses."""
    session = _NoRedirectSession()
    # Requests through a proxy would connect to the proxy rather than the
    # push service, bypassing the address check, so ignore proxy settings
    # from the environment.
    session.trust_env = False
    adapter = _PublicAddressAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
