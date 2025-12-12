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

"""Tests for xandikos.apache."""

import unittest
from unittest.mock import Mock
from xml.etree import ElementTree as ET
import asyncio

from xandikos import apache


class ExecutablePropertyTests(unittest.TestCase):
    """Tests for ExecutableProperty."""

    def test_property_attributes(self):
        """Test ExecutableProperty attributes."""
        prop = apache.ExecutableProperty()
        self.assertEqual(prop.name, "{http://apache.org/dav/props/}executable")
        self.assertIsNone(prop.resource_type)
        self.assertFalse(prop.live)

    def test_get_value_true(self):
        """Test get_value when resource is executable."""

        async def run_test():
            prop = apache.ExecutableProperty()
            resource = Mock()
            resource.get_is_executable.return_value = True

            el = ET.Element("test")
            await prop.get_value("/test.sh", resource, el, {})

            self.assertEqual(el.text, "T")
            resource.get_is_executable.assert_called_once()

        asyncio.run(run_test())

    def test_get_value_false(self):
        """Test get_value when resource is not executable."""

        async def run_test():
            prop = apache.ExecutableProperty()
            resource = Mock()
            resource.get_is_executable.return_value = False

            el = ET.Element("test")
            await prop.get_value("/test.txt", resource, el, {})

            self.assertEqual(el.text, "F")
            resource.get_is_executable.assert_called_once()

        asyncio.run(run_test())

    def test_set_value_true(self):
        """Test set_value with 'T' (true)."""

        async def run_test():
            prop = apache.ExecutableProperty()
            resource = Mock()

            el = ET.Element("test")
            el.text = "T"
            await prop.set_value("/test.sh", resource, el)

            resource.set_is_executable.assert_called_once_with(True)

        asyncio.run(run_test())

    def test_set_value_false(self):
        """Test set_value with 'F' (false)."""

        async def run_test():
            prop = apache.ExecutableProperty()
            resource = Mock()

            el = ET.Element("test")
            el.text = "F"
            await prop.set_value("/test.txt", resource, el)

            resource.set_is_executable.assert_called_once_with(False)

        asyncio.run(run_test())

    def test_set_value_invalid(self):
        """Test set_value with invalid value."""

        async def run_test():
            prop = apache.ExecutableProperty()
            resource = Mock()

            el = ET.Element("test")
            el.text = "X"  # Invalid value

            with self.assertRaises(ValueError) as cm:
                await prop.set_value("/test", resource, el)

            self.assertIn("invalid executable setting 'X'", str(cm.exception))
            resource.set_is_executable.assert_not_called()

        asyncio.run(run_test())

    def test_set_value_empty(self):
        """Test set_value with empty/None value."""

        async def run_test():
            prop = apache.ExecutableProperty()
            resource = Mock()

            el = ET.Element("test")
            el.text = None

            with self.assertRaises(ValueError) as cm:
                await prop.set_value("/test", resource, el)

            self.assertIn("invalid executable setting None", str(cm.exception))
            resource.set_is_executable.assert_not_called()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
