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

"""Tests for xandikos.vcard."""

import unittest

from xandikos.vcard import VCardFile, CardDAVFilter

EXAMPLE_VCARD1 = b"""\
BEGIN:VCARD
VERSION:3.0
EMAIL;TYPE=INTERNET:jeffrey@osafoundation.org
EMAIL;TYPE=INTERNET:jeffery@example.org
ORG:Open Source Applications Foundation
FN:Jeffrey Harris
N:Harris;Jeffrey;;;
END:VCARD
"""


class ParseVcardTests(unittest.TestCase):
    def test_validate(self):
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        fi.validate()

    def test_get_index(self):
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        # Test indexing of FN property
        fn_values = list(fi._get_index("P=FN"))
        self.assertEqual(fn_values, [b"Jeffrey Harris"])

        # Test indexing of EMAIL property
        email_values = list(fi._get_index("P=EMAIL"))
        self.assertEqual(
            sorted(email_values), [b"jeffery@example.org", b"jeffrey@osafoundation.org"]
        )

        # Test indexing of ORG property
        org_values = list(fi._get_index("P=ORG"))
        self.assertEqual(org_values, [b"Open Source Applications Foundation"])

        # Test indexing of non-existent property
        tel_values = list(fi._get_index("P=TEL"))
        self.assertEqual(tel_values, [])


class CardDAVFilterTests(unittest.TestCase):
    def test_empty_filter(self):
        """Test that empty filter matches everything."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()
        self.assertTrue(filter.check("test.vcf", fi))

    def test_prop_filter_exists(self):
        """Test filtering for property existence."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()

        # Filter for existing property
        filter.add_property_filter("FN")
        self.assertTrue(filter.check("test.vcf", fi))

        # Filter for non-existing property
        filter2 = CardDAVFilter()
        filter2.add_property_filter("TEL")
        self.assertFalse(filter2.check("test.vcf", fi))

    def test_prop_filter_is_not_defined(self):
        """Test filtering for property non-existence."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()

        # Filter for non-existing property
        filter.add_property_filter("TEL", is_not_defined=True)
        self.assertTrue(filter.check("test.vcf", fi))

        # Filter for existing property
        filter2 = CardDAVFilter()
        filter2.add_property_filter("FN", is_not_defined=True)
        self.assertFalse(filter2.check("test.vcf", fi))

    def test_text_match_contains(self):
        """Test text matching with contains."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()
        prop_filter = filter.add_property_filter("FN")
        prop_filter.add_text_match("Jeffrey", match_type="contains")
        self.assertTrue(filter.check("test.vcf", fi))

        filter2 = CardDAVFilter()
        prop_filter2 = filter2.add_property_filter("FN")
        prop_filter2.add_text_match("John", match_type="contains")
        self.assertFalse(filter2.check("test.vcf", fi))

    def test_text_match_equals(self):
        """Test text matching with equals."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()
        prop_filter = filter.add_property_filter("FN")
        prop_filter.add_text_match("Jeffrey Harris", match_type="equals")
        self.assertTrue(filter.check("test.vcf", fi))

    def test_multiple_filters_anyof(self):
        """Test multiple filters with anyof test."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()
        filter.test = any

        # One matches, one doesn't
        prop_filter = filter.add_property_filter("FN")
        prop_filter.add_text_match("Jeffrey", match_type="contains")
        filter.add_property_filter("TEL")  # Doesn't exist
        self.assertTrue(filter.check("test.vcf", fi))

    def test_multiple_filters_allof(self):
        """Test multiple filters with allof test."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")
        filter = CardDAVFilter()
        filter.test = all

        # Both must match
        prop_filter = filter.add_property_filter("FN")
        prop_filter.add_text_match("Jeffrey", match_type="contains")
        filter.add_property_filter("EMAIL")
        self.assertTrue(filter.check("test.vcf", fi))

        # One doesn't match
        filter2 = CardDAVFilter()
        filter2.test = all
        filter2.add_property_filter("FN")
        filter2.add_property_filter("TEL")  # Doesn't exist
        self.assertFalse(filter2.check("test.vcf", fi))

    def test_index_keys(self):
        """Test that index keys are correctly generated."""
        filter = CardDAVFilter()
        filter.add_property_filter("FN")
        filter.add_property_filter("EMAIL")
        filter.add_property_filter(
            "TEL", is_not_defined=True
        )  # Should not be in index keys

        keys = filter.index_keys()
        self.assertEqual(sorted(keys), [["P=EMAIL"], ["P=FN"]])

    def test_check_from_indexes(self):
        """Test checking from indexes."""
        filter = CardDAVFilter()
        prop_filter = filter.add_property_filter("FN")
        prop_filter.add_text_match("Jeffrey", match_type="contains")

        # Test with matching index
        indexes = {"P=FN": [b"Jeffrey Harris"]}
        self.assertTrue(filter.check_from_indexes("test.vcf", indexes))

        # Test with non-matching index
        indexes2 = {"P=FN": [b"John Doe"]}
        self.assertFalse(filter.check_from_indexes("test.vcf", indexes2))

        # Test with missing index
        indexes3 = {}
        self.assertFalse(filter.check_from_indexes("test.vcf", indexes3))

    def test_param_filter(self):
        """Test parameter filtering."""
        fi = VCardFile([EXAMPLE_VCARD1], "text/vcard")

        # Test param exists
        filter = CardDAVFilter()
        prop_filter = filter.add_property_filter("EMAIL")
        prop_filter.add_param_filter("TYPE")
        self.assertTrue(filter.check("test.vcf", fi))

        # Test param doesn't exist
        filter2 = CardDAVFilter()
        prop_filter2 = filter2.add_property_filter("EMAIL")
        prop_filter2.add_param_filter("PREF")
        self.assertFalse(filter2.check("test.vcf", fi))

        # Test param is-not-defined
        filter3 = CardDAVFilter()
        prop_filter3 = filter3.add_property_filter("EMAIL")
        prop_filter3.add_param_filter("PREF", is_not_defined=True)
        self.assertTrue(filter3.check("test.vcf", fi))

        # Test param text match
        filter4 = CardDAVFilter()
        prop_filter4 = filter4.add_property_filter("EMAIL")
        param_filter4 = prop_filter4.add_param_filter("TYPE")
        param_filter4.add_text_match("INTERNET", match_type="equals")
        self.assertTrue(filter4.check("test.vcf", fi))
