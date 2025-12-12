# Xandikos
# Copyright (C) 2025 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Tests for xandikos.wsgi_helpers."""

import unittest
from unittest.mock import Mock

from xandikos import wsgi_helpers


class WellknownRedirectorTests(unittest.TestCase):
    """Tests for WellknownRedirector."""

    def setUp(self):
        self.inner_app = Mock()
        self.dav_root = "/dav/"
        self.redirector = wsgi_helpers.WellknownRedirector(
            self.inner_app, self.dav_root
        )

    def test_redirect_caldav(self):
        """Test redirection of /.well-known/caldav."""
        environ = {"SCRIPT_NAME": "", "PATH_INFO": "/.well-known/caldav"}
        start_response = Mock()

        result = self.redirector(environ, start_response)

        # Should redirect to dav root
        start_response.assert_called_once_with("302 Found", [("Location", "/dav/")])
        self.assertEqual(result, [])
        # Inner app should not be called
        self.inner_app.assert_not_called()

    def test_redirect_carddav(self):
        """Test redirection of /.well-known/carddav."""
        environ = {"SCRIPT_NAME": "", "PATH_INFO": "/.well-known/carddav"}
        start_response = Mock()

        result = self.redirector(environ, start_response)

        # Should redirect to dav root
        start_response.assert_called_once_with("302 Found", [("Location", "/dav/")])
        self.assertEqual(result, [])
        # Inner app should not be called
        self.inner_app.assert_not_called()

    def test_redirect_with_script_name(self):
        """Test redirection with SCRIPT_NAME set."""
        environ = {"SCRIPT_NAME": "/app", "PATH_INFO": "/.well-known/caldav"}
        start_response = Mock()

        # The code normalizes the path to include SCRIPT_NAME
        # But still checks against the wellknown paths
        self.redirector(environ, start_response)

        # Should pass through to inner app since normalized path is /app/.well-known/caldav
        self.inner_app.assert_called_once_with(environ, start_response)
        start_response.assert_not_called()

    def test_no_redirect_regular_path(self):
        """Test that regular paths are not redirected."""
        environ = {"SCRIPT_NAME": "", "PATH_INFO": "/calendar/events"}
        start_response = Mock()

        # Set up inner app to return something
        self.inner_app.return_value = ["response body"]

        result = self.redirector(environ, start_response)

        # Should pass through to inner app
        self.inner_app.assert_called_once_with(environ, start_response)
        self.assertEqual(result, ["response body"])

    def test_no_redirect_similar_path(self):
        """Test that similar but not exact paths are not redirected."""
        environ = {"SCRIPT_NAME": "", "PATH_INFO": "/.well-known/caldav/extra"}
        start_response = Mock()

        # Set up inner app to return something
        self.inner_app.return_value = ["response body"]

        result = self.redirector(environ, start_response)

        # Should pass through to inner app
        self.inner_app.assert_called_once_with(environ, start_response)
        self.assertEqual(result, ["response body"])

    def test_path_normalization(self):
        """Test that paths are normalized before checking."""
        environ = {
            "SCRIPT_NAME": "",
            "PATH_INFO": "/.well-known//caldav",  # Double slash
        }
        start_response = Mock()

        result = self.redirector(environ, start_response)

        # After normalization, path becomes /.well-known/caldav
        start_response.assert_called_once_with("302 Found", [("Location", "/dav/")])
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
