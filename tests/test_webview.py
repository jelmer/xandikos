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

import unittest
import unittest.mock

from xandikos import webdav
from xandikos.webview import (
    parent_url,
    parse_form,
    request_collection_url,
    wants_html,
)


class ParentUrlTests(unittest.TestCase):
    def test_root(self):
        self.assertIsNone(parent_url("http://host/"))

    def test_strips_one_segment(self):
        self.assertEqual("http://host/", parent_url("http://host/user/"))
        self.assertEqual("http://host/user/", parent_url("http://host/user/calendar/"))

    def test_collapses_double_slashes(self):
        self.assertEqual("http://host/user/", parent_url("http://host//user//cal/"))

    def test_drops_query_and_fragment(self):
        self.assertEqual("http://host/", parent_url("http://host/user/?month=2026-05"))


class WantsHtmlTests(unittest.TestCase):
    def test_browser(self):
        self.assertTrue(wants_html(webdav.parse_accept_header("text/html,*/*;q=0.8")))

    def test_calendar_client(self):
        self.assertFalse(wants_html(webdav.parse_accept_header("text/calendar")))

    def test_tie_goes_to_native_type(self):
        self.assertFalse(wants_html(webdav.parse_accept_header("*/*"), "text/vcard"))

    def test_native_type_preferred(self):
        self.assertFalse(
            wants_html(
                webdav.parse_accept_header("text/calendar, */*;q=0.5"),
                "text/calendar",
            )
        )

    def test_browser_with_native_type(self):
        self.assertTrue(
            wants_html(
                webdav.parse_accept_header("text/html,*/*;q=0.8"), "text/calendar"
            )
        )


class ParseFormTests(unittest.TestCase):
    def test_form(self):
        self.assertEqual(
            {"action": "delete", "name": "b", "empty": ""},
            parse_form(
                [b"action=delete&name=a&name=b&empty="],
                "application/x-www-form-urlencoded",
            ),
        )

    def test_not_a_form(self):
        self.assertIsNone(parse_form([b"BEGIN:VCARD"], "text/vcard"))


class RequestCollectionUrlTests(unittest.TestCase):
    def test_collapses_slashes(self):
        request = unittest.mock.Mock(url="http://host//user//calendars/cal?x=1")
        self.assertEqual(
            "http://host/user/calendars/cal/", request_collection_url(request)
        )
