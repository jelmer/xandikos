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
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, AsyncMock
from wsgiref.util import setup_testing_defaults

from xandikos.webdav import WebDAVApp
from xandikos.web import MultiUserXandikosBackend


class MockBackend:
    """Mock backend for testing."""

    def __init__(self):
        self.set_principal_calls = []
        self.resources = {}

    def set_principal(self, user):
        self.set_principal_calls.append(user)

    def get_resource(self, path):
        return self.resources.get(path)


class AuthenticationTests(unittest.TestCase):
    """Tests for authentication header handling."""

    def setUp(self):
        self.backend = MockBackend()
        self.app = WebDAVApp(self.backend)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        # Reset the event loop to avoid affecting other tests
        asyncio.set_event_loop(asyncio.new_event_loop())

    def test_wsgi_x_remote_user_header(self):
        """Test that HTTP_X_REMOTE_USER is handled in WSGI."""
        environ = {
            "REQUEST_METHOD": "OPTIONS",
            "PATH_INFO": "/",
            "HTTP_X_REMOTE_USER": "testuser",
        }
        setup_testing_defaults(environ)

        # Mock the resource
        mock_resource = MagicMock()
        mock_resource.resource_types = []
        self.backend.resources["/"] = mock_resource

        # Mock start_response
        responses = []

        def start_response(status, headers):
            responses.append((status, headers))
            return lambda x: None

        # Call the WSGI handler
        list(self.app.handle_wsgi_request(environ, start_response))

        # Check that we got a response
        self.assertTrue(len(responses) > 0)

        # Check that set_principal was called with the user
        self.assertEqual(["testuser"], self.backend.set_principal_calls)

        # Check that REMOTE_USER was set in environ for the request
        # (The environ is recreated in handle_wsgi_request, so we can't check it directly)

    def test_wsgi_no_remote_user(self):
        """Test WSGI without authentication header."""
        environ = {
            "REQUEST_METHOD": "OPTIONS",
            "PATH_INFO": "/",
        }
        setup_testing_defaults(environ)

        # Mock the resource
        mock_resource = MagicMock()
        mock_resource.resource_types = []
        self.backend.resources["/"] = mock_resource

        # Mock start_response
        responses = []

        def start_response(status, headers):
            responses.append((status, headers))
            return lambda x: None

        # Call the WSGI handler
        self.app.handle_wsgi_request(environ, start_response)

        # Check that set_principal was NOT called
        self.assertEqual([], self.backend.set_principal_calls)

    def test_aiohttp_x_remote_user_header(self):
        """Test that X-Remote-User header is handled in aiohttp."""
        # Create a mock aiohttp request
        mock_request = AsyncMock()
        mock_headers = MagicMock()
        mock_headers.get.side_effect = (
            lambda k, d=None: "aiohttpuser" if k == "X-Remote-User" else d
        )
        mock_headers.__getitem__.side_effect = (
            lambda k: "aiohttpuser" if k == "X-Remote-User" else None
        )
        mock_request.headers = mock_headers
        mock_request.method = "OPTIONS"
        mock_request.path = "/"
        mock_request.url = "http://example.com/"
        mock_request.raw_path = "/"
        mock_request.match_info = {"path_info": "/"}
        mock_request.content_type = "text/plain"
        mock_request.content_length = 0
        mock_request.can_read_body = False

        # Mock the resource
        mock_resource = MagicMock()
        mock_resource.resource_types = []
        self.backend.resources["/"] = mock_resource

        # Call the aiohttp handler
        self.loop.run_until_complete(self.app.aiohttp_handler(mock_request, "/"))

        # Check that set_principal was called with the user
        self.assertEqual(["aiohttpuser"], self.backend.set_principal_calls)

    def test_aiohttp_no_remote_user(self):
        """Test aiohttp without authentication header."""
        # Create a mock aiohttp request
        mock_request = AsyncMock()
        mock_headers = MagicMock()
        mock_headers.get.return_value = None
        mock_request.headers = mock_headers
        mock_request.method = "OPTIONS"
        mock_request.path = "/"
        mock_request.url = "http://example.com/"
        mock_request.raw_path = "/"
        mock_request.match_info = {"path_info": "/"}
        mock_request.content_type = "text/plain"
        mock_request.content_length = 0
        mock_request.can_read_body = False

        # Mock the resource
        mock_resource = MagicMock()
        mock_resource.resource_types = []
        self.backend.resources["/"] = mock_resource

        # Call the aiohttp handler
        self.loop.run_until_complete(self.app.aiohttp_handler(mock_request, "/"))

        # Check that set_principal was NOT called
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
        # Reset the event loop to avoid affecting other tests
        asyncio.set_event_loop(asyncio.new_event_loop())

    def test_multiuser_backend_with_aiohttp_auth(self):
        """Test MultiUserXandikosBackend with aiohttp authentication."""
        backend = MultiUserXandikosBackend(self.d)
        app = WebDAVApp(backend)

        # Create a mock aiohttp request with auth
        mock_request = AsyncMock()
        mock_headers = MagicMock()
        mock_headers.get.side_effect = (
            lambda k, d=None: "alice" if k == "X-Remote-User" else d
        )
        mock_headers.__getitem__.side_effect = (
            lambda k: "alice" if k == "X-Remote-User" else None
        )
        mock_request.headers = mock_headers
        mock_request.method = "PROPFIND"
        mock_request.path = "/alice/"
        mock_request.url = "http://example.com/alice/"
        mock_request.raw_path = "/alice/"
        mock_request.match_info = {"path_info": "/alice/"}
        mock_request.content_type = "application/xml"
        mock_request.content_length = 0
        mock_request.can_read_body = False

        # Call the aiohttp handler
        self.loop.run_until_complete(app.aiohttp_handler(mock_request, "/"))

        # Check that the principal was created
        resource = backend.get_resource("/alice/")
        self.assertIsNotNone(resource)
        # _mark_as_principal normalizes the path, removing trailing slashes
        self.assertIn("/alice", backend._user_principals)
