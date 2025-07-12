# Xandikos
# Copyright (C) 2022 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

from ..carddav import NAMESPACE, AddressDataProperty
from ..vcard import VCardFile, CardDAVFilter, parse_filter
from ..webdav import ET
from .test_vcard import EXAMPLE_VCARD1


class TestApplyFilter(unittest.TestCase):
    def test_parse_filter(self):
        """Test parsing filter XML into CardDAVFilter object."""
        el = ET.Element("{%s}filter" % NAMESPACE)
        el.set("test", "anyof")
        pf = ET.SubElement(el, "{%s}prop-filter" % NAMESPACE)
        pf.set("name", "FN")
        tm = ET.SubElement(pf, "{%s}text-match" % NAMESPACE)
        tm.set("collation", "i;unicode-casemap")
        tm.set("match-type", "contains")
        tm.text = "Jeffrey"

        # Parse the filter
        filter_obj = parse_filter(el, CardDAVFilter())

        # Test that it was parsed correctly
        self.assertEqual(filter_obj.test, any)
        self.assertEqual(len(filter_obj.property_filters), 1)
        prop_filter = filter_obj.property_filters[0]
        self.assertEqual(prop_filter.name, "FN")
        self.assertEqual(len(prop_filter.text_matches), 1)
        text_match = prop_filter.text_matches[0]
        self.assertEqual(text_match.text, "Jeffrey")
        self.assertEqual(text_match.match_type, "contains")

        # Test that it actually filters correctly
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        self.assertTrue(filter_obj.check("test.vcf", fi))


class TestAddressDataProperty(unittest.TestCase):
    def test_supported_on_with_vcard(self):
        """Test that supported_on returns True for vcard resources."""
        prop = AddressDataProperty()

        class VCardResource:
            def get_content_type(self):
                return "text/vcard"

        self.assertTrue(prop.supported_on(VCardResource()))

    def test_supported_on_with_non_vcard(self):
        """Test that supported_on returns False for non-vcard resources."""
        prop = AddressDataProperty()

        class NonVCardResource:
            def get_content_type(self):
                return "text/plain"

        self.assertFalse(prop.supported_on(NonVCardResource()))

    def test_supported_on_with_missing_content_type(self):
        """Test that supported_on handles resources without content type gracefully."""
        prop = AddressDataProperty()

        class ResourceWithoutContentType:
            def get_content_type(self):
                raise KeyError("No content type")

        # This should not raise an exception, but return False
        self.assertFalse(prop.supported_on(ResourceWithoutContentType()))
