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

"""Tests for xandikos.davcommon."""

import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
import asyncio

from xandikos import davcommon, webdav


class SubbedPropertyTests(unittest.TestCase):
    """Tests for SubbedProperty."""

    def test_get_value_ext_not_implemented(self):
        """Test that get_value_ext raises NotImplementedError."""
        prop = davcommon.SubbedProperty()
        prop.name = "test-property"

        async def run_test():
            with self.assertRaises(NotImplementedError):
                await prop.get_value_ext(
                    "href", "resource", ET.Element("el"), {}, ET.Element("requested")
                )

        asyncio.run(run_test())


class GetPropertiesWithDataTests(unittest.TestCase):
    """Tests for get_properties_with_data."""

    def test_get_properties_with_data(self):
        """Test that get_properties_with_data includes the data property."""
        data_property = Mock(spec=davcommon.SubbedProperty)
        data_property.name = "test-property"

        href = "/test"
        resource = Mock()
        properties = {"prop1": Mock(), "prop2": Mock()}
        environ = {}
        requested = ET.Element("requested")

        async def run_test():
            # Mock webdav.get_properties to return some values
            async def mock_get_properties(href, resource, props, environ, requested):
                self.assertIn(data_property.name, props)
                self.assertEqual(props[data_property.name], data_property)
                yield "propstat1"
                yield "propstat2"

            with patch("xandikos.webdav.get_properties", mock_get_properties):
                result = []
                async for ps in davcommon.get_properties_with_data(
                    data_property, href, resource, properties, environ, requested
                ):
                    result.append(ps)

                self.assertEqual(result, ["propstat1", "propstat2"])

        asyncio.run(run_test())


class MockMultiGetReporter(davcommon.MultiGetReporter):
    """Mock implementation of MultiGetReporter for testing."""

    name = "test-report"

    def __init__(self):
        self.data_property = Mock(spec=davcommon.SubbedProperty)
        self.data_property.name = "test-data-property"


class MultiGetReporterTests(unittest.TestCase):
    """Tests for MultiGetReporter."""

    def setUp(self):
        self.reporter = MockMultiGetReporter()

    def test_report_with_hrefs(self):
        """Test report with href elements."""

        async def run_test():
            # Create test body with href elements
            body = ET.Element("body")
            prop_el = ET.SubElement(body, "{DAV:}prop")
            ET.SubElement(prop_el, "{DAV:}propname")

            href1_el = ET.SubElement(body, "{DAV:}href")
            href1_el.text = "/test1"
            href2_el = ET.SubElement(body, "{DAV:}href")
            href2_el.text = "/test2"

            # Mock resources_by_hrefs
            resource1 = Mock()
            resource2 = Mock()

            def mock_resources_by_hrefs(hrefs):
                self.assertEqual(hrefs, ["/test1", "/test2"])
                return [("/test1", resource1), ("/test2", resource2)]

            # Mock get_properties_with_data
            async def mock_get_properties_with_data(
                data_prop, href, resource, props, environ, requested
            ):
                if href == "/test1":
                    yield webdav.PropStatus("200 OK", None, ET.Element("prop"))
                else:
                    yield webdav.PropStatus("200 OK", None, ET.Element("prop"))

            with patch(
                "xandikos.davcommon.get_properties_with_data",
                mock_get_properties_with_data,
            ):
                # Call the decorated method which returns a response
                response = await self.reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=mock_resources_by_hrefs,
                    properties={},
                    base_href="/",
                    resource=Mock(),
                    depth="0",
                    strict=True,
                )

                # The multistatus decorator returns a Response object
                self.assertIsInstance(response, webdav.Response)
                self.assertEqual(response.status, 207)
                # Parse the XML response to verify content
                xml_content = b"".join(response.body)
                root = ET.fromstring(xml_content)
                responses = root.findall("{DAV:}response")
                self.assertEqual(len(responses), 2)

        asyncio.run(run_test())

    def test_report_with_missing_resource(self):
        """Test report with a missing resource."""

        async def run_test():
            # Create test body with href element
            body = ET.Element("body")
            href_el = ET.SubElement(body, "{DAV:}href")
            href_el.text = "/missing"

            # Mock resources_by_hrefs to return None for resource
            def mock_resources_by_hrefs(hrefs):
                return [("/missing", None)]

            response = await self.reporter.report(
                environ={},
                body=body,
                resources_by_hrefs=mock_resources_by_hrefs,
                properties={},
                base_href="/",
                resource=Mock(),
                depth="0",
                strict=True,
            )

            # The multistatus decorator returns a Response object
            self.assertIsInstance(response, webdav.Response)
            self.assertEqual(response.status, 207)
            # Parse the XML response to verify content
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)
            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)
            # Verify 404 status
            status = responses[0].find("{DAV:}status")
            self.assertIn("404 Not Found", status.text)

        asyncio.run(run_test())

    def test_report_no_requested_implies_allprop(self):
        """Test that no requested element implies allprop."""

        async def run_test():
            # Create test body with only href element (no prop/allprop/propname)
            body = ET.Element("body")
            href_el = ET.SubElement(body, "{DAV:}href")
            href_el.text = "/test"

            resource = Mock()

            def mock_resources_by_hrefs(hrefs):
                return [("/test", resource)]

            # Track what requested element is passed
            requested_element = None

            async def mock_get_properties_with_data(
                data_prop, href, res, props, environ, requested
            ):
                nonlocal requested_element
                requested_element = requested
                yield webdav.PropStatus("200 OK", None, ET.Element("prop"))

            with patch(
                "xandikos.davcommon.get_properties_with_data",
                mock_get_properties_with_data,
            ):
                await self.reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=mock_resources_by_hrefs,
                    properties={},
                    base_href="/",
                    resource=Mock(),
                    depth="0",
                    strict=True,
                )

            # Verify allprop was used
            self.assertIsNotNone(requested_element)
            self.assertEqual(requested_element.tag, "{DAV:}allprop")

        asyncio.run(run_test())

    def test_report_unknown_tag_strict(self):
        """Test report with unknown tag in strict mode."""

        async def run_test():
            # Create test body with unknown element
            body = ET.Element("body")
            ET.SubElement(body, "{TEST:}unknown")

            # Mock nonfatal_bad_request to verify it's called
            with patch("xandikos.webdav.nonfatal_bad_request") as mock_bad_request:
                await self.reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=lambda hrefs: [],
                    properties={},
                    base_href="/",
                    resource=Mock(),
                    depth="0",
                    strict=True,
                )

                # Verify nonfatal_bad_request was called
                mock_bad_request.assert_called_once()
                args = mock_bad_request.call_args[0]
                self.assertIn("Unknown tag", args[0])
                self.assertIn("{TEST:}unknown", args[0])
                self.assertTrue(args[1])  # strict=True

        asyncio.run(run_test())

    def test_report_accepts_any_depth(self):
        """Test that base multiget implementation accepts any depth value.

        The base MultiGetReporter class does not validate the Depth header.
        Subclasses (CalDAV, CardDAV) handle depth validation according to
        their specific RFC requirements.
        """

        async def run_test():
            # Create minimal test body
            body = ET.Element("body")
            href_el = ET.SubElement(body, "{DAV:}href")
            href_el.text = "/test"

            resource = Mock()

            def mock_resources_by_hrefs(hrefs):
                return [("/test", resource)]

            async def mock_get_properties_with_data(
                data_prop, href, res, props, environ, requested
            ):
                yield webdav.PropStatus("200 OK", None, ET.Element("prop"))

            with patch(
                "xandikos.davcommon.get_properties_with_data",
                mock_get_properties_with_data,
            ):
                # Test with depth "0" - should work
                response = await self.reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=mock_resources_by_hrefs,
                    properties={},
                    base_href="/",
                    resource=Mock(),
                    depth="0",
                    strict=True,
                )
                self.assertEqual(response.status, 207)

                # Test with depth "1" - should also work (no validation)
                response = await self.reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=mock_resources_by_hrefs,
                    properties={},
                    base_href="/",
                    resource=Mock(),
                    depth="1",
                    strict=True,
                )
                self.assertEqual(response.status, 207)

                # Test with depth "infinity" - should also work (no validation)
                response = await self.reporter.report(
                    environ={},
                    body=body,
                    resources_by_hrefs=mock_resources_by_hrefs,
                    properties={},
                    base_href="/",
                    resource=Mock(),
                    depth="infinity",
                    strict=True,
                )
                self.assertEqual(response.status, 207)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
