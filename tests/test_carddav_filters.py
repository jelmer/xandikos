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

"""Comprehensive filter combination tests for CardDAV addressbook-query (RFC 6352 §10.5)."""

import unittest

from xandikos.vcard import CardDAVFilter, VCardFile


class CardDAVFilterCombinationTests(unittest.TestCase):
    """Test various combinations of CardDAV filters (RFC 6352 Section 10.5)."""

    def setUp(self):
        """Set up test vCard data."""
        # Test contact 1: Alice with email and phone
        self.vcard1 = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Alice Smith\r\n",
                b"N:Smith;Alice;;;\r\n",
                b"EMAIL:alice@example.com\r\n",
                b"TEL;TYPE=WORK:+1-555-1234\r\n",
                b"ORG:Example Corp\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        # Test contact 2: Bob without email
        self.vcard2 = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Bob Jones\r\n",
                b"N:Jones;Bob;;;\r\n",
                b"TEL;TYPE=HOME:+1-555-5678\r\n",
                b"ORG:Acme Inc\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        # Test contact 3: Charlie with multiple properties
        self.vcard3 = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Charlie Brown\r\n",
                b"N:Brown;Charlie;;;\r\n",
                b"EMAIL:charlie@example.org\r\n",
                b"TEL;TYPE=WORK:+1-555-9999\r\n",
                b"TEL;TYPE=CELL:+1-555-0000\r\n",
                b"TITLE:Developer\r\n",
                b"ORG:Tech Solutions\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

    def test_prop_filter_fn_contains(self):
        """Test prop-filter with text-match contains.

        RFC 6352 Section 10.5.1: Text match with contains.
        """
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "Smith", collation="i;unicode-casemap", match_type="contains"
        )

        # vcard1 has "Alice Smith"
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2 has "Bob Jones" - no match
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))

    def test_prop_filter_fn_equals(self):
        """Test prop-filter with text-match equals."""
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "Bob Jones", collation="i;unicode-casemap", match_type="equals"
        )

        self.assertFalse(filter_obj.check("vcard1.vcf", self.vcard1))
        self.assertTrue(filter_obj.check("vcard2.vcf", self.vcard2))

    def test_prop_filter_fn_starts_with(self):
        """Test prop-filter with text-match starts-with."""
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "Alice", collation="i;unicode-casemap", match_type="starts-with"
        )

        # vcard1: "Alice Smith" starts with "Alice"
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2: "Bob Jones" doesn't start with "Alice"
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))

    def test_prop_filter_fn_ends_with(self):
        """Test prop-filter with text-match ends-with."""
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "Brown", collation="i;unicode-casemap", match_type="ends-with"
        )

        # vcard3: "Charlie Brown" ends with "Brown"
        self.assertTrue(filter_obj.check("vcard3.vcf", self.vcard3))
        # vcard1: "Alice Smith" doesn't end with "Brown"
        self.assertFalse(filter_obj.check("vcard1.vcf", self.vcard1))

    def test_prop_filter_is_not_defined(self):
        """Test prop-filter with is-not-defined.

        RFC 6352 Section 10.5.1: Property must not exist.
        """
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("EMAIL", is_not_defined=True)

        # vcard1 has EMAIL
        self.assertFalse(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2 has no EMAIL
        self.assertTrue(filter_obj.check("vcard2.vcf", self.vcard2))

    def test_prop_filter_is_defined(self):
        """Test prop-filter without is-not-defined (property must exist)."""
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("EMAIL")

        # vcard1 has EMAIL
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2 has no EMAIL
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))

    def test_multiple_prop_filters_anyof(self):
        """Test multiple prop-filters with anyof test (OR logic).

        RFC 6352 Section 10.5: Default test is anyof.
        """
        filter_obj = CardDAVFilter()
        # anyof is the default
        filter_obj.add_property_filter("FN").add_text_match(
            "Alice", match_type="contains"
        )
        filter_obj.add_property_filter("FN").add_text_match(
            "Charlie", match_type="contains"
        )

        # vcard1: has "Alice"
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2: has neither "Alice" nor "Charlie"
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))
        # vcard3: has "Charlie"
        self.assertTrue(filter_obj.check("vcard3.vcf", self.vcard3))

    def test_multiple_prop_filters_allof(self):
        """Test multiple prop-filters with allof test (AND logic).

        RFC 6352 Section 10.5: Test attribute determines AND/OR.
        """
        filter_obj = CardDAVFilter()
        filter_obj.test = all  # allof (AND logic)
        filter_obj.add_property_filter("EMAIL")
        filter_obj.add_property_filter("ORG").add_text_match(
            "Example", match_type="contains"
        )

        # vcard1: has EMAIL and "Example Corp"
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2: no EMAIL
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))
        # vcard3: has EMAIL but "Tech Solutions" not "Example"
        self.assertFalse(filter_obj.check("vcard3.vcf", self.vcard3))

    def test_param_filter_type(self):
        """Test param-filter for TYPE parameter.

        RFC 6352 Section 10.5.2: Parameter filtering.
        """
        filter_obj = CardDAVFilter()
        prop_filter = filter_obj.add_property_filter("TEL")
        prop_filter.add_param_filter("TYPE").add_text_match(
            "WORK", match_type="contains"
        )

        # vcard1: has TEL with TYPE=WORK
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2: has TEL with TYPE=HOME
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))
        # vcard3: has TEL with TYPE=WORK
        self.assertTrue(filter_obj.check("vcard3.vcf", self.vcard3))

    def test_param_filter_is_not_defined(self):
        """Test param-filter with is-not-defined."""
        filter_obj = CardDAVFilter()
        prop_filter = filter_obj.add_property_filter("TEL")
        prop_filter.add_param_filter("TYPE", is_not_defined=True)

        # All test vcards have TEL with TYPE parameter
        self.assertFalse(filter_obj.check("vcard1.vcf", self.vcard1))
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))
        self.assertFalse(filter_obj.check("vcard3.vcf", self.vcard3))

    def test_text_match_case_insensitive(self):
        """Test text-match with case insensitivity.

        RFC 6352 Section 10.5.1: Collation determines case sensitivity.
        """
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "SMITH", collation="i;unicode-casemap", match_type="contains"
        )

        # vcard1 has "Alice Smith" - should match with case-insensitive
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))

    def test_text_match_negate_condition(self):
        """Test text-match with negate-condition.

        RFC 6352 Section 10.5.1: Negate-condition inverts the match.
        """
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "Alice", match_type="contains", negate_condition=True
        )

        # vcard1: has "Alice" - negated, should not match
        self.assertFalse(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2: doesn't have "Alice" - negated, should match
        self.assertTrue(filter_obj.check("vcard2.vcf", self.vcard2))

    def test_combined_property_and_text_filters(self):
        """Test combination of property existence and text filtering."""
        filter_obj = CardDAVFilter()
        filter_obj.test = all  # AND logic
        filter_obj.add_property_filter("EMAIL")
        filter_obj.add_property_filter("TEL")
        filter_obj.add_property_filter("ORG").add_text_match(
            "Corp", match_type="contains"
        )

        # vcard1: has EMAIL, TEL, and "Example Corp"
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        # vcard2: no EMAIL
        self.assertFalse(filter_obj.check("vcard2.vcf", self.vcard2))
        # vcard3: has EMAIL and TEL but "Tech Solutions" not "Corp"
        self.assertFalse(filter_obj.check("vcard3.vcf", self.vcard3))

    def test_empty_filter(self):
        """Test filter with no property filters matches all."""
        filter_obj = CardDAVFilter()

        # Should match all vcards
        self.assertTrue(filter_obj.check("vcard1.vcf", self.vcard1))
        self.assertTrue(filter_obj.check("vcard2.vcf", self.vcard2))
        self.assertTrue(filter_obj.check("vcard3.vcf", self.vcard3))


class CardDAVFilterEdgeCasesTests(unittest.TestCase):
    """Test edge cases for CardDAV filters."""

    def test_filter_with_unicode_in_fn(self):
        """Test filtering vCards with Unicode characters."""
        vcard = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Ren\xc3\xa9 Dupont\r\n",
                b"N:Dupont;Ren\xc3\xa9;;;\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("FN").add_text_match(
            "René", collation="i;unicode-casemap", match_type="contains"
        )
        self.assertTrue(filter_obj.check("vcard.vcf", vcard))

    def test_filter_with_empty_property(self):
        """Test filtering when property exists but is empty."""
        vcard = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Test User\r\n",
                b"N:User;Test;;;\r\n",
                b"NOTE:\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        # Property is defined (even if empty)
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("NOTE")
        self.assertTrue(filter_obj.check("vcard.vcf", vcard))

    def test_filter_multiple_email_addresses(self):
        """Test filtering when multiple instances of same property exist."""
        vcard = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Multi Email\r\n",
                b"N:Email;Multi;;;\r\n",
                b"EMAIL:work@example.com\r\n",
                b"EMAIL:personal@gmail.com\r\n",
                b"EMAIL:other@company.org\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        # Should match if ANY email matches
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("EMAIL").add_text_match(
            "gmail", collation="i;unicode-casemap", match_type="contains"
        )
        self.assertTrue(filter_obj.check("vcard.vcf", vcard))

    def test_filter_org_structured_property(self):
        """Test filtering on structured ORG property."""
        vcard = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:Structured Org\r\n",
                b"N:Org;Structured;;;\r\n",
                b"ORG:Example Corporation;Engineering Department\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        # Should match text in any part of structured property
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("ORG").add_text_match(
            "Engineering", match_type="contains"
        )
        self.assertTrue(filter_obj.check("vcard.vcf", vcard))

    def test_filter_n_property(self):
        """Test filtering on N (structured name) property."""
        vcard = VCardFile(
            [
                b"BEGIN:VCARD\r\n",
                b"VERSION:3.0\r\n",
                b"FN:John Doe\r\n",
                b"N:Doe;John;Michael;Dr.;Jr.\r\n",
                b"END:VCARD\r\n",
            ],
            "text/vcard",
        )

        # Should match last name
        filter_obj = CardDAVFilter()
        filter_obj.add_property_filter("N").add_text_match("Doe", match_type="contains")
        self.assertTrue(filter_obj.check("vcard.vcf", vcard))


if __name__ == "__main__":
    unittest.main()
