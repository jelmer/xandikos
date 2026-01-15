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

"""Tests for xandikos.sync."""

import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
import asyncio

from xandikos import sync, webdav


class SyncTokenTests(unittest.TestCase):
    """Tests for SyncToken."""

    def test_init(self):
        """Test SyncToken initialization."""
        token = sync.SyncToken("test-token-123")
        self.assertEqual(token.token, "test-token-123")

    def test_aselement(self):
        """Test SyncToken.aselement()."""
        token = sync.SyncToken("test-token-456")
        element = token.aselement()

        self.assertEqual(element.tag, "{DAV:}sync-token")
        self.assertEqual(element.text, "test-token-456")


class InvalidTokenTests(unittest.TestCase):
    """Tests for InvalidToken exception."""

    def test_init(self):
        """Test InvalidToken initialization."""
        exc = sync.InvalidToken("bad-token")
        self.assertEqual(exc.token, "bad-token")


class SyncCollectionReporterTests(unittest.TestCase):
    """Tests for SyncCollectionReporter."""

    def setUp(self):
        self.reporter = sync.SyncCollectionReporter()

    def test_report_basic_sync(self):
        """Test basic sync-collection report."""

        async def run_test():
            # Create request body
            body = ET.Element("body")
            sync_token_el = ET.SubElement(body, "{DAV:}sync-token")
            sync_token_el.text = "old-token"
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"
            prop_el = ET.SubElement(body, "{DAV:}prop")
            ET.SubElement(prop_el, "{DAV:}getetag")

            # Mock resource
            resource = Mock()
            resource.get_sync_token.return_value = "new-token"

            # Mock differences
            new_resource = Mock()
            resource.iter_differences_since.return_value = [
                ("file1.txt", None, new_resource),  # New file
                ("file2.txt", Mock(), None),  # Deleted file
            ]

            # Mock property handling
            async def mock_get_property_from_element(href, res, props, env, el):
                return webdav.PropStatus("200 OK", None, ET.Element("{DAV:}getetag"))

            with patch(
                "xandikos.webdav.get_property_from_element",
                mock_get_property_from_element,
            ):
                response = await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

            # Check response
            self.assertIsInstance(response, webdav.Response)
            self.assertEqual(response.status, 207)

            # Parse XML response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            # Should have responses for changes and a sync token
            responses = root.findall("{DAV:}response")
            sync_tokens = root.findall("{DAV:}sync-token")

            self.assertEqual(len(responses), 2)  # Two file changes
            self.assertEqual(len(sync_tokens), 1)
            self.assertEqual(sync_tokens[0].text, "new-token")

        asyncio.run(run_test())

    def test_report_invalid_sync_level(self):
        """Test sync-collection report with invalid sync level."""

        async def run_test():
            body = ET.Element("body")
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "infinite"  # Not supported

            resource = Mock()

            with self.assertRaises(webdav.BadRequestError) as cm:
                await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

            self.assertIn("sync level 'infinite' unsupported", str(cm.exception))

        asyncio.run(run_test())

    def test_report_not_implemented(self):
        """Test sync-collection report when sync is not implemented."""

        async def run_test():
            body = ET.Element("body")
            sync_token_el = ET.SubElement(body, "{DAV:}sync-token")
            sync_token_el.text = "old-token"
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"

            resource = Mock()
            resource.get_sync_token.return_value = "new-token"
            resource.iter_differences_since.side_effect = NotImplementedError()

            response = await self.reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=lambda hrefs: [],
                properties={},
                href="/collection/",
                resource=resource,
                depth="1",
                strict=True,
            )

            # Check response
            self.assertIsInstance(response, webdav.Response)
            self.assertEqual(response.status, 207)

            # Parse XML response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            # Should have one response with 403 Forbidden
            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

            status = responses[0].find("{DAV:}status")
            self.assertIn("403 Forbidden", status.text)

            # Check error element
            error = responses[0].find("{DAV:}error")
            self.assertIsNotNone(error)
            sync_error = error.find("{DAV:}sync-traversal-supported")
            self.assertIsNotNone(sync_error)

        asyncio.run(run_test())

    def test_report_invalid_token(self):
        """Test sync-collection report with invalid token."""

        async def run_test():
            body = ET.Element("body")
            sync_token_el = ET.SubElement(body, "{DAV:}sync-token")
            sync_token_el.text = "invalid-token"
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"

            resource = Mock()
            resource.get_sync_token.return_value = "new-token"
            resource.iter_differences_since.side_effect = sync.InvalidToken(
                "invalid-token"
            )

            with self.assertRaises(webdav.PreconditionFailure) as cm:
                await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

            self.assertIn("invalid-token", str(cm.exception))

        asyncio.run(run_test())

    def test_report_with_limit(self):
        """Test sync-collection report with limit.

        RFC 6578 Section 3.3: The limit element allows clients to limit
        the number of member resources in the response.
        """

        async def run_test():
            body = ET.Element("body")
            sync_token_el = ET.SubElement(body, "{DAV:}sync-token")
            sync_token_el.text = "old-token"
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"
            limit_el = ET.SubElement(body, "{DAV:}limit")
            nresults_el = ET.SubElement(limit_el, "{DAV:}nresults")
            nresults_el.text = "1"
            prop_el = ET.SubElement(body, "{DAV:}prop")
            ET.SubElement(prop_el, "{DAV:}getetag")

            resource = Mock()
            resource.get_sync_token.return_value = "new-token"

            # Return more changes than the limit
            resource.iter_differences_since.return_value = [
                ("file1.txt", None, Mock()),
                ("file2.txt", None, Mock()),
                ("file3.txt", None, Mock()),
            ]

            # Mock property handling
            async def mock_get_property_from_element(href, res, props, env, el):
                return webdav.PropStatus("200 OK", None, ET.Element("{DAV:}getetag"))

            with patch(
                "xandikos.webdav.get_property_from_element",
                mock_get_property_from_element,
            ):
                response = await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

            # Parse XML response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            # Limit is now working - only 1 response should be returned
            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

            # Verify sync token is still present
            sync_tokens = root.findall("{DAV:}sync-token")
            self.assertEqual(len(sync_tokens), 1)
            self.assertEqual(sync_tokens[0].text, "new-token")

        asyncio.run(run_test())

    def test_report_unknown_tag(self):
        """Test sync-collection report with unknown tag."""

        async def run_test():
            body = ET.Element("body")
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"
            ET.SubElement(body, "{TEST:}unknown")

            resource = Mock()
            resource.get_sync_token.return_value = "new-token"
            resource.iter_differences_since.return_value = []

            with patch("xandikos.webdav.nonfatal_bad_request") as mock_bad_request:
                await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

                # Verify nonfatal_bad_request was called
                mock_bad_request.assert_called_once()
                args = mock_bad_request.call_args[0]
                self.assertIn("unknown tag", args[0])
                self.assertIn("{TEST:}unknown", args[0])

        asyncio.run(run_test())

    def test_report_initial_sync(self):
        """Test initial sync-collection with empty token.

        RFC 6578 Section 3.4: Initial synchronization uses an empty
        DAV:sync-token element to get all current collection members.
        """

        async def run_test():
            body = ET.Element("body")
            sync_token_el = ET.SubElement(body, "{DAV:}sync-token")
            sync_token_el.text = ""  # Empty token for initial sync
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"
            prop_el = ET.SubElement(body, "{DAV:}prop")
            ET.SubElement(prop_el, "{DAV:}getetag")

            resource = Mock()
            resource.get_sync_token.return_value = "token-1"

            # All current resources returned for initial sync
            new_resource1 = Mock()
            new_resource2 = Mock()
            resource.iter_differences_since.return_value = [
                ("file1.txt", None, new_resource1),  # None = not in old state
                ("file2.txt", None, new_resource2),
            ]

            # Mock property handling
            async def mock_get_property_from_element(href, res, props, env, el):
                return webdav.PropStatus("200 OK", None, ET.Element("{DAV:}getetag"))

            with patch(
                "xandikos.webdav.get_property_from_element",
                mock_get_property_from_element,
            ):
                response = await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

            # Parse XML response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            # Should return all current members
            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 2)

            # Verify new sync token is provided
            sync_tokens = root.findall("{DAV:}sync-token")
            self.assertEqual(len(sync_tokens), 1)
            self.assertEqual(sync_tokens[0].text, "token-1")

            # Verify called with empty token
            resource.iter_differences_since.assert_called_once_with("", "token-1")

        asyncio.run(run_test())

    def test_report_collection_member_changes(self):
        """Test sync-collection with nested collection changes.

        RFC 6578 Section 3.5: Collections within collections are reported
        when they are created, modified, or deleted.
        """

        async def run_test():
            body = ET.Element("body")
            sync_token_el = ET.SubElement(body, "{DAV:}sync-token")
            sync_token_el.text = "old-token"
            sync_level_el = ET.SubElement(body, "{DAV:}sync-level")
            sync_level_el.text = "1"
            prop_el = ET.SubElement(body, "{DAV:}prop")
            ET.SubElement(prop_el, "{DAV:}resourcetype")

            resource = Mock()
            resource.get_sync_token.return_value = "new-token"

            # Mix of file and collection changes
            new_file = Mock()
            new_collection = Mock()
            resource.iter_differences_since.return_value = [
                ("newfile.txt", None, new_file),  # New file
                ("subcollection/", None, new_collection),  # New collection
                ("oldcollection/", Mock(), None),  # Deleted collection
            ]

            # Mock property handling
            async def mock_get_property_from_element(href, res, props, env, el):
                prop_el = ET.Element("{DAV:}resourcetype")
                if res == new_collection:
                    ET.SubElement(prop_el, "{DAV:}collection")
                return webdav.PropStatus("200 OK", None, prop_el)

            with patch(
                "xandikos.webdav.get_property_from_element",
                mock_get_property_from_element,
            ):
                response = await self.reporter.report(
                    environ={},
                    request_body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    href="/collection/",
                    resource=resource,
                    depth="1",
                    strict=True,
                )

            # Parse XML response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 3)

            # Verify deleted collection returns 404
            hrefs = [r.find("{DAV:}href").text for r in responses]
            statuses = [
                r.find("{DAV:}status").text
                if r.find("{DAV:}status") is not None
                else None
                for r in responses
            ]

            # One should be the deleted collection with 404
            deleted_idx = hrefs.index("/collection/oldcollection/")
            self.assertIn("404", statuses[deleted_idx])

        asyncio.run(run_test())


class SyncTokenPropertyTests(unittest.TestCase):
    """Tests for SyncTokenProperty."""

    def test_property_attributes(self):
        """Test SyncTokenProperty attributes."""
        prop = sync.SyncTokenProperty()
        self.assertEqual(prop.name, "{DAV:}sync-token")
        self.assertEqual(prop.resource_type, webdav.COLLECTION_RESOURCE_TYPE)
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)

    def test_get_value(self):
        """Test SyncTokenProperty.get_value()."""

        async def run_test():
            prop = sync.SyncTokenProperty()
            resource = Mock()
            resource.get_sync_token.return_value = "test-sync-token"

            el = ET.Element("test")
            await prop.get_value("/collection/", resource, el, {})

            self.assertEqual(el.text, "test-sync-token")
            resource.get_sync_token.assert_called_once()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
