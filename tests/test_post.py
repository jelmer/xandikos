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

"""Tests for RFC 5995 POST to Add Members to WebDAV Collections."""

import asyncio
import unittest

from xandikos import webdav
from xandikos.webdav import ET


class AddMemberPropertyTests(unittest.TestCase):
    """Tests for AddMemberProperty (RFC 5995 Section 3.2.1)."""

    def test_property_name(self):
        """Test add-member property name."""
        prop = webdav.AddMemberProperty()
        self.assertEqual(prop.name, "{DAV:}add-member")

    def test_property_attributes(self):
        """Test add-member property attributes.

        RFC 5995 Section 3.2.1: The add-member property identifies the
        URL where POST requests should be sent to add new members.
        """
        prop = webdav.AddMemberProperty()
        self.assertTrue(prop.live)
        self.assertEqual(prop.resource_type, webdav.COLLECTION_RESOURCE_TYPE)

    def test_get_value_collection_url(self):
        """Test add-member property value for collection.

        RFC 5995 Section 3.2.1: The property contains a DAV:href element
        pointing to the URL for POST operations (typically the collection itself).
        """

        async def run_test():
            prop = webdav.AddMemberProperty()

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/collection/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            # RFC 5995 uses "." to indicate the collection itself
            self.assertEqual(hrefs[0].text, "/collection/")

        asyncio.run(run_test())

    def test_get_value_relative_resolution(self):
        """Test add-member with relative URL resolution."""

        async def run_test():
            prop = webdav.AddMemberProperty()

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/default/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            # "." should resolve to the base href
            self.assertEqual(hrefs[0].text, "/calendars/user1/default/")

        asyncio.run(run_test())

    def test_get_value_nested_collection(self):
        """Test add-member on nested collection."""

        async def run_test():
            prop = webdav.AddMemberProperty()

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/a/b/c/", resource, el, {})

            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/a/b/c/")

        asyncio.run(run_test())


class AddMemberFeatureTests(unittest.TestCase):
    """Tests for RFC 5995 add-member feature constant."""

    def test_feature_constant(self):
        """Test add-member feature constant.

        RFC 5995 Section 6: The feature identifier for add-member support.
        """
        self.assertEqual(webdav.ADD_MEMBER_FEATURE, "add-member")


if __name__ == "__main__":
    unittest.main()
