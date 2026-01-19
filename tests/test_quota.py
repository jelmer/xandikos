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

"""Tests for xandikos.quota (RFC 4331)."""

import asyncio
import unittest

from xandikos import quota
from xandikos.webdav import ET


class QuotaAvailableBytesPropertyTests(unittest.TestCase):
    """Tests for QuotaAvailableBytesProperty (RFC 4331 Section 3)."""

    def test_property_name(self):
        """Test quota-available-bytes property name."""
        prop = quota.QuotaAvailableBytesProperty()
        self.assertEqual(prop.name, "{DAV:}quota-available-bytes")

    def test_property_attributes(self):
        """Test quota-available-bytes property attributes."""
        prop = quota.QuotaAvailableBytesProperty()
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)
        self.assertIsNone(prop.resource_type)

    def test_get_value(self):
        """Test quota-available-bytes get_value method.

        RFC 4331 Section 3: Contains the number of bytes available
        to the user without exceeding quota.
        """

        async def run_test():
            prop = quota.QuotaAvailableBytesProperty()

            class MockResource:
                def get_quota_available_bytes(self):
                    return "1073741824"  # 1 GB

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/test", resource, el, {})

            self.assertEqual(el.text, "1073741824")

        asyncio.run(run_test())


class QuotaUsedBytesPropertyTests(unittest.TestCase):
    """Tests for QuotaUsedBytesProperty (RFC 4331 Section 4)."""

    def test_property_name(self):
        """Test quota-used-bytes property name."""
        prop = quota.QuotaUsedBytesProperty()
        self.assertEqual(prop.name, "{DAV:}quota-used-bytes")

    def test_property_attributes(self):
        """Test quota-used-bytes property attributes."""
        prop = quota.QuotaUsedBytesProperty()
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)
        self.assertIsNone(prop.resource_type)

    def test_get_value(self):
        """Test quota-used-bytes get_value method.

        RFC 4331 Section 4: Contains the number of bytes used by
        the resource and all its children.
        """

        async def run_test():
            prop = quota.QuotaUsedBytesProperty()

            class MockResource:
                def get_quota_used_bytes(self):
                    return "524288000"  # 500 MB

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/test", resource, el, {})

            self.assertEqual(el.text, "524288000")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
