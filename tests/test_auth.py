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

"""Tests for authentication handling in xandikos."""

import asyncio
import gc
import tempfile
import shutil
import unittest
import warnings
from unittest.mock import MagicMock, AsyncMock
from wsgiref.util import setup_testing_defaults

from xandikos.webdav import WebDAVApp, AUTHENTICATED_USER_ATTR
from xandikos.multi_user import MultiUserFilesystemBackend


class MockBackend:
    """Mock backend for testing."""

    def __init__(self):
        self.set_principal_calls = []
        self.resources = {}

    def set_principal(self, user):
        self.set_principal_calls.append(user)

    def get_resource(self, path):
        return self.resources.get(path)


def _make_aiohttp_request(header_map, *, remote=None, extras=None):
    """Build a MagicMock modelling the aiohttp Request surface we touch."""
    mock_request = AsyncMock()
    mock_headers = MagicMock()
    mock_headers.get.side_effect = lambda k, d=None: header_map.get(k, d)
    mock_headers.__getitem__.side_effect = lambda k: header_map[k]
    mock_headers.__contains__.side_effect = lambda k: k in header_map
    mock_request.headers = mock_headers
    mock_request.method = "OPTIONS"
    mock_request.path = "/"
    mock_request.url = "http://example.com/"
    mock_request.raw_path = "/"
    mock_request.match_info = {"path_info": "/"}
    mock_request.content_type = "text/plain"
    mock_request.content_length = 0
    mock_request.can_read_body = False
    mock_request.remote = remote

    storage = dict(extras or {})
    mock_request.get = storage.get
    mock_request.__getitem__ = lambda self_, k: storage[k]
    mock_request.__setitem__ = lambda self_, k, v: storage.__setitem__(k, v)
    mock_request.__contains__ = lambda self_, k: k in storage
    return mock_request


class WSGIAuthenticationTests(unittest.TestCase):
    """WSGI-side handling of REMOTE_USER and X-Remote-User."""

    def setUp(self):
        self.backend = MockBackend()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        mock_resource = MagicMock()
        mock_resource.resource_types = []
        self.backend.resources["/"] = mock_resource

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def _run_wsgi(self, app, environ):
        setup_testing_defaults(environ)
        responses = []

        def start_response(status, headers):
            responses.append((status, headers))
            return lambda x: None

        list(app.handle_wsgi_request(environ, start_response))
        self.assertTrue(responses)

    def test_genuine_remote_user_env_is_honored(self):
        """REMOTE_USER set by an authenticating WSGI middleware is trusted."""
        app = WebDAVApp(self.backend)
        environ = {
            "REQUEST_METHOD": "OPTIONS",
            "PATH_INFO": "/",
            "REMOTE_USER": "wsgiuser",
        }
        self._run_wsgi(app, environ)
        self.assertEqual(["wsgiuser"], self.backend.set_principal_calls)

    def test_http_x_remote_user_ignored_by_default(self):
        """HTTP_X_REMOTE_USER (from a client X-Remote-User header) is ignored.

        Without an explicit trust opt-in the header is client-supplied and
        must not be allowed to name the authenticated principal (CVE-worthy
        impersonation otherwise).
        """
        app = WebDAVApp(self.backend)
        environ = {
            "REQUEST_METHOD": "OPTIONS",
            "PATH_INFO": "/",
            "HTTP_X_REMOTE_USER": "attacker",
        }
        self._run_wsgi(app, environ)
        self.assertEqual([], self.backend.set_principal_calls)

    def test_http_x_remote_user_honored_when_peer_trusted(self):
        """With trusted-hosts + matching REMOTE_ADDR, the header is trusted."""
        app = WebDAVApp(self.backend, trusted_x_remote_user_hosts=["10.0.0.0/8"])
        environ = {
            "REQUEST_METHOD": "OPTIONS",
            "PATH_INFO": "/",
            "HTTP_X_REMOTE_USER": "proxied",
            "REMOTE_ADDR": "10.1.2.3",
        }
        self._run_wsgi(app, environ)
        self.assertEqual(["proxied"], self.backend.set_principal_calls)

    def test_http_x_remote_user_rejected_when_peer_untrusted(self):
        """Trusted-hosts is a CIDR gate: a non-matching peer is rejected."""
        app = WebDAVApp(self.backend, trusted_x_remote_user_hosts=["10.0.0.0/8"])
        environ = {
            "REQUEST_METHOD": "OPTIONS",
            "PATH_INFO": "/",
            "HTTP_X_REMOTE_USER": "attacker",
            "REMOTE_ADDR": "192.0.2.5",
        }
        self._run_wsgi(app, environ)
        self.assertEqual([], self.backend.set_principal_calls)

    def test_wsgi_no_remote_user(self):
        """Without any signal there is no authenticated principal."""
        app = WebDAVApp(self.backend)
        environ = {"REQUEST_METHOD": "OPTIONS", "PATH_INFO": "/"}
        self._run_wsgi(app, environ)
        self.assertEqual([], self.backend.set_principal_calls)


class AiohttpAuthenticationTests(unittest.TestCase):
    """aiohttp-side handling of X-Remote-User and in-process markers."""

    def setUp(self):
        self.backend = MockBackend()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        mock_resource = MagicMock()
        mock_resource.resource_types = []
        self.backend.resources["/"] = mock_resource

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def _dispatch(self, app, request):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            warnings.simplefilter("ignore", ResourceWarning)
            self.loop.run_until_complete(app.aiohttp_handler(request, "/"))
            gc.collect()

    def test_x_remote_user_header_ignored_by_default(self):
        """Client-supplied X-Remote-User is rejected without trust config."""
        app = WebDAVApp(self.backend)
        request = _make_aiohttp_request(
            {"X-Remote-User": "attacker"}, remote="203.0.113.4"
        )
        self._dispatch(app, request)
        self.assertEqual([], self.backend.set_principal_calls)

    def test_x_remote_user_header_honored_when_peer_trusted(self):
        """Trusted-proxy CIDR enables the header."""
        app = WebDAVApp(self.backend, trusted_x_remote_user_hosts=["127.0.0.0/8"])
        request = _make_aiohttp_request(
            {"X-Remote-User": "proxied"}, remote="127.0.0.1"
        )
        self._dispatch(app, request)
        self.assertEqual(["proxied"], self.backend.set_principal_calls)

    def test_x_remote_user_header_rejected_when_peer_untrusted(self):
        """A request from outside the trusted CIDR is not honored."""
        app = WebDAVApp(self.backend, trusted_x_remote_user_hosts=["127.0.0.0/8"])
        request = _make_aiohttp_request(
            {"X-Remote-User": "attacker"}, remote="198.51.100.7"
        )
        self._dispatch(app, request)
        self.assertEqual([], self.backend.set_principal_calls)

    def test_in_process_marker_beats_header(self):
        """Middleware may set an in-process marker on the request.

        This is the mechanism basic_auth_middleware uses. It must take
        precedence over any client-supplied X-Remote-User (which is left
        untrusted), so that an attacker cannot set X-Remote-User to
        override the actually-authenticated identity.
        """
        app = WebDAVApp(self.backend)
        request = _make_aiohttp_request(
            {"X-Remote-User": "attacker"},
            remote="203.0.113.4",
            extras={AUTHENTICATED_USER_ATTR: "authed"},
        )
        self._dispatch(app, request)
        self.assertEqual(["authed"], self.backend.set_principal_calls)

    def test_aiohttp_no_remote_user(self):
        app = WebDAVApp(self.backend)
        request = _make_aiohttp_request({}, remote="127.0.0.1")
        self._dispatch(app, request)
        self.assertEqual([], self.backend.set_principal_calls)


class IntegrationTests(unittest.TestCase):
    """Integration tests with real backends."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        shutil.rmtree(self.d)
        self.loop.close()
        asyncio.set_event_loop(None)

    def _dispatch(self, app, request):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            warnings.simplefilter("ignore", ResourceWarning)
            self.loop.run_until_complete(app.aiohttp_handler(request, "/"))
            gc.collect()

    def test_multiuser_rejects_untrusted_x_remote_user(self):
        """Multi-user + no trust config: X-Remote-User cannot create alice."""
        backend = MultiUserFilesystemBackend(self.d)
        app = WebDAVApp(backend)

        request = _make_aiohttp_request(
            {"X-Remote-User": "alice"}, remote="203.0.113.4"
        )
        request.method = "PROPFIND"
        request.path = "/alice/"
        request.url = "http://example.com/alice/"
        request.raw_path = "/alice/"
        request.match_info = {"path_info": "/alice/"}
        request.content_type = "application/xml"

        self._dispatch(app, request)

        # No principal was created, since the header is untrusted.
        self.assertIsNone(backend.get_resource("/alice/"))
        self.assertNotIn("/alice", backend._user_principals)

    def test_multiuser_honors_x_remote_user_from_trusted_peer(self):
        """Multi-user + explicit trust: header creates & auths the principal."""
        backend = MultiUserFilesystemBackend(self.d)
        app = WebDAVApp(backend, trusted_x_remote_user_hosts=["127.0.0.0/8", "::1"])

        request = _make_aiohttp_request({"X-Remote-User": "alice"}, remote="127.0.0.1")
        request.method = "PROPFIND"
        request.path = "/alice/"
        request.url = "http://example.com/alice/"
        request.raw_path = "/alice/"
        request.match_info = {"path_info": "/alice/"}
        request.content_type = "application/xml"

        self._dispatch(app, request)

        resource = backend.get_resource("/alice/")
        self.assertIsNotNone(resource)
        self.assertIn("/alice", backend._user_principals)

    def test_multiuser_in_process_marker_creates_principal(self):
        """basic_auth_middleware's in-process marker also creates principals."""
        backend = MultiUserFilesystemBackend(self.d)
        app = WebDAVApp(backend)

        request = _make_aiohttp_request(
            {},
            remote="203.0.113.4",
            extras={AUTHENTICATED_USER_ATTR: "bob"},
        )
        request.method = "PROPFIND"
        request.path = "/bob/"
        request.url = "http://example.com/bob/"
        request.raw_path = "/bob/"
        request.match_info = {"path_info": "/bob/"}
        request.content_type = "application/xml"

        self._dispatch(app, request)

        resource = backend.get_resource("/bob/")
        self.assertIsNotNone(resource)
        self.assertIn("/bob", backend._user_principals)
