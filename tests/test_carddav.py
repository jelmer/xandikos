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

import asyncio
import os
import tempfile
import unittest

from xandikos.carddav import NAMESPACE, AddressDataProperty
from xandikos.store.git import TreeGitStore
from xandikos.vcard import VCardFile, CardDAVFilter, parse_filter
from xandikos.web import AddressbookCollection, SingleUserFilesystemBackend
from xandikos import webdav
from xandikos.webdav import ET, PreconditionFailure
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


class AddressbookQueryReporterTests(unittest.TestCase):
    """Tests for addressbook-query REPORT (RFC 6352 Section 8.6)."""

    def test_report_name(self):
        """Test addressbook-query reporter name."""
        from xandikos.carddav import AddressbookQueryReporter

        reporter = AddressbookQueryReporter()
        self.assertEqual(
            reporter.name, "{urn:ietf:params:xml:ns:carddav}addressbook-query"
        )

    def test_report_resource_type(self):
        """Test addressbook-query supported resource type."""
        from xandikos.carddav import (
            AddressbookQueryReporter,
            ADDRESSBOOK_RESOURCE_TYPE,
        )

        reporter = AddressbookQueryReporter()
        self.assertEqual(reporter.resource_type, ADDRESSBOOK_RESOURCE_TYPE)


class AddressbookMultigetReporterTests(unittest.TestCase):
    """Tests for addressbook-multiget REPORT (RFC 6352 Section 8.7)."""

    def test_report_name(self):
        """Test addressbook-multiget reporter name."""
        from xandikos.carddav import AddressbookMultiGetReporter

        reporter = AddressbookMultiGetReporter()
        self.assertEqual(
            reporter.name, "{urn:ietf:params:xml:ns:carddav}addressbook-multiget"
        )

    def test_report_resource_type(self):
        """Test addressbook-multiget supported resource type."""
        from xandikos.carddav import (
            AddressbookMultiGetReporter,
            ADDRESSBOOK_RESOURCE_TYPE,
        )

        reporter = AddressbookMultiGetReporter()
        self.assertEqual(reporter.resource_type, ADDRESSBOOK_RESOURCE_TYPE)

    def test_depth_header_ignored(self):
        """Test that the Depth header is ignored, even in strict mode.

        RFC 6352 Section 8.7 says addressbook-multiget "MUST include a
        Depth: 0 header", but the examples in that section use Depth: 1 and
        errata EID 4610 recommends Depth: 1. Depth is meaningless for a
        multiget, so non-zero values are accepted.
        """
        from xandikos.carddav import AddressbookMultiGetReporter

        async def run_test():
            reporter = AddressbookMultiGetReporter()
            body = ET.Element("body")

            for depth in ("0", "1", "infinity"):
                response = await reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    base_href="/",
                    resource=None,
                    depth=depth,
                    strict=True,
                )
                self.assertEqual(response.status, 207)

        asyncio.run(run_test())


class TestAddressbookValidation(unittest.TestCase):
    """Test that addressbook collections only accept vCard files."""

    def test_addressbook_create_member_validation(self):
        """Test that AddressbookCollection.create_member validates content types."""
        with tempfile.TemporaryDirectory() as tempdir:
            store_path = os.path.join(tempdir, "store")
            store = TreeGitStore.create(store_path)
            store.load_extra_file_handler(VCardFile)
            backend = SingleUserFilesystemBackend(tempdir)
            addressbook = AddressbookCollection(backend, "/addressbook", store)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Test that non-vCard content types are rejected
                with self.assertRaises(PreconditionFailure) as context:
                    loop.run_until_complete(
                        addressbook.create_member(
                            "test.ics", [b"data"], "text/calendar"
                        )
                    )
                self.assertEqual(
                    "{%s}supported-address-data" % NAMESPACE,
                    context.exception.precondition,
                )
                self.assertIn("vCard", str(context.exception.description))
                self.assertIn("text/calendar", str(context.exception.description))

                # Test other non-vCard types
                with self.assertRaises(PreconditionFailure):
                    loop.run_until_complete(
                        addressbook.create_member("test.txt", [b"data"], "text/plain")
                    )

                # Test that vCard content types are accepted
                for i, content_type in enumerate(
                    ("text/vcard", "text/x-vcard", "text/directory")
                ):
                    name, etag = loop.run_until_complete(
                        addressbook.create_member(
                            f"test{i}.vcf", [EXAMPLE_VCARD1], content_type
                        )
                    )
                    self.assertTrue(name.endswith(".vcf"))
                    self.assertIsNotNone(etag)

            finally:
                loop.close()
