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

"""Tests for RFC 3253 expand-property REPORT."""

import asyncio
import unittest
from unittest.mock import Mock

from xandikos import webdav
from xandikos.webdav import ET


class ExpandPropertyReporterTests(unittest.TestCase):
    """Tests for ExpandPropertyReporter (RFC 3253 Section 3.8)."""

    def test_reporter_name(self):
        """Test expand-property reporter name."""
        reporter = webdav.ExpandPropertyReporter()
        self.assertEqual(reporter.name, "{DAV:}expand-property")

    def test_report_simple_property(self):
        """Test expand-property with simple property without hrefs.

        RFC 3253 Section 3.8: The expand-property REPORT is used to
        retrieve properties and recursively expand properties containing
        DAV:href elements. Properties without hrefs are returned as-is.
        """

        async def run_test():
            reporter = webdav.ExpandPropertyReporter()

            # Create request body
            body = ET.Element("{DAV:}expand-property")
            prop_el = ET.SubElement(body, "{DAV:}property")
            prop_el.set("name", "{DAV:}resourcetype")

            # Mock resource
            resource = Mock()
            resource.get_resource_types = Mock(return_value=["{DAV:}collection"])

            # Mock property
            class ResourceTypeProperty(webdav.Property):
                name = "{DAV:}resourcetype"

                async def get_value(self, href, resource, el, environ):
                    for rt in resource.get_resource_types():
                        ET.SubElement(el, rt)

            properties = {"{DAV:}resourcetype": ResourceTypeProperty()}

            response = await reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=lambda hrefs: [],
                properties=properties,
                href="/test",
                resource=resource,
                depth="0",
                strict=True,
            )

            # Parse response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            # Verify response structure
            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

            # Verify href
            href_el = responses[0].find("{DAV:}href")
            self.assertEqual(href_el.text, "/test")

            # Verify property was returned
            propstat = responses[0].find("{DAV:}propstat")
            self.assertIsNotNone(propstat)
            prop = propstat.find("{DAV:}prop")
            self.assertIsNotNone(prop)
            resourcetype = prop.find("{DAV:}resourcetype")
            self.assertIsNotNone(resourcetype)
            # Check that the collection element is present
            collection = resourcetype.find("{DAV:}collection")
            self.assertIsNotNone(collection)

        asyncio.run(run_test())

    def test_report_property_with_href(self):
        """Test expand-property with property containing href.

        RFC 3253 Section 3.8: Properties containing DAV:href elements
        should be expanded by fetching properties of the referenced resource.
        """

        async def run_test():
            reporter = webdav.ExpandPropertyReporter()

            # Create request body
            body = ET.Element("{DAV:}expand-property")
            prop_el = ET.SubElement(body, "{DAV:}property")
            prop_el.set("name", "{DAV:}owner")
            # Request to expand the owner property
            child_prop_el = ET.SubElement(prop_el, "{DAV:}property")
            child_prop_el.set("name", "{DAV:}displayname")

            # Mock main resource
            resource = Mock()

            # Mock owner resource
            owner_resource = Mock()
            owner_resource.get_displayname = Mock(return_value="Owner Name")

            # Mock owner property
            class OwnerProperty(webdav.Property):
                name = "{DAV:}owner"

                async def get_value(self, href, resource, el, environ):
                    href_el = ET.SubElement(el, "{DAV:}href")
                    href_el.text = "/principals/owner/"

            # Mock displayname property - use child element instead of text
            class DisplayNameProperty(webdav.Property):
                name = "{DAV:}displayname"

                async def get_value(self, href, resource, el, environ):
                    # Use a child element to hold the value for expand-property
                    value_el = ET.SubElement(el, "{DAV:}value")
                    value_el.text = resource.get_displayname()

            properties = {
                "{DAV:}owner": OwnerProperty(),
                "{DAV:}displayname": DisplayNameProperty(),
            }

            def resources_by_hrefs(hrefs):
                hrefs_list = list(hrefs)
                if "/principals/owner/" in hrefs_list:
                    return [("/principals/owner/", owner_resource)]
                return []

            response = await reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=resources_by_hrefs,
                properties=properties,
                href="/test",
                resource=resource,
                depth="0",
                strict=True,
            )

            # Parse response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            # Verify response structure
            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

            # Verify the owner property was expanded
            propstat = responses[0].find("{DAV:}propstat")
            prop = propstat.find("{DAV:}prop")
            owner = prop.find("{DAV:}owner")
            self.assertIsNotNone(owner)

            # Should contain expanded response with displayname
            expanded_response = owner.find("{DAV:}response")
            self.assertIsNotNone(expanded_response)

            # Verify expanded href
            expanded_href = expanded_response.find("{DAV:}href")
            self.assertEqual(expanded_href.text, "/principals/owner/")

            # Verify expanded property
            expanded_propstat = expanded_response.find("{DAV:}propstat")
            expanded_prop = expanded_propstat.find("{DAV:}prop")
            expanded_displayname = expanded_prop.find("{DAV:}displayname")
            self.assertIsNotNone(expanded_displayname)
            # Check the value child element
            value_el = expanded_displayname.find("{DAV:}value")
            self.assertIsNotNone(value_el)
            self.assertEqual(value_el.text, "Owner Name")

        asyncio.run(run_test())

    def test_report_multiple_properties(self):
        """Test expand-property with multiple properties."""

        async def run_test():
            reporter = webdav.ExpandPropertyReporter()

            # Create request body
            body = ET.Element("{DAV:}expand-property")
            prop1 = ET.SubElement(body, "{DAV:}property")
            prop1.set("name", "{DAV:}resourcetype")
            prop2 = ET.SubElement(body, "{DAV:}property")
            prop2.set("name", "{DAV:}current-user-principal")

            # Mock resource
            resource = Mock()
            resource.get_resource_types = Mock(return_value=["{DAV:}collection"])
            resource.get_owner = Mock(return_value="/principals/user1/")

            class ResourceTypeProperty(webdav.Property):
                name = "{DAV:}resourcetype"

                async def get_value(self, href, resource, el, environ):
                    for rt in resource.get_resource_types():
                        ET.SubElement(el, rt)

            class CurrentUserPrincipalProperty(webdav.Property):
                name = "{DAV:}current-user-principal"

                async def get_value(self, href, resource, el, environ):
                    href_el = ET.SubElement(el, "{DAV:}href")
                    href_el.text = resource.get_owner()

            properties = {
                "{DAV:}resourcetype": ResourceTypeProperty(),
                "{DAV:}current-user-principal": CurrentUserPrincipalProperty(),
            }

            response = await reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=lambda hrefs: [],
                properties=properties,
                href="/test",
                resource=resource,
                depth="0",
                strict=True,
            )

            # Parse response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

            # Verify both properties were returned
            propstat = responses[0].find("{DAV:}propstat")
            prop = propstat.find("{DAV:}prop")
            self.assertIsNotNone(prop.find("{DAV:}resourcetype"))
            self.assertIsNotNone(prop.find("{DAV:}current-user-principal"))

        asyncio.run(run_test())

    def test_report_property_without_name_attribute(self):
        """Test expand-property with property element missing name attribute.

        RFC 3253 Section 3.8: Property elements must have a name attribute.
        Invalid requests should be handled gracefully.
        """

        async def run_test():
            reporter = webdav.ExpandPropertyReporter()

            # Create invalid request body (property without name)
            body = ET.Element("{DAV:}expand-property")
            ET.SubElement(body, "{DAV:}property")  # No name attribute

            resource = Mock()

            response = await reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=lambda hrefs: [],
                properties={},
                href="/test",
                resource=resource,
                depth="0",
                strict=False,  # Non-strict mode to avoid exception
            )

            # Should return a response without error
            self.assertEqual(response.status, 207)

        asyncio.run(run_test())

    def test_report_unknown_property(self):
        """Test expand-property requesting unknown property."""

        async def run_test():
            reporter = webdav.ExpandPropertyReporter()

            # Create request body
            body = ET.Element("{DAV:}expand-property")
            prop_el = ET.SubElement(body, "{DAV:}property")
            prop_el.set("name", "{DAV:}nonexistent")

            resource = Mock()

            response = await reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=lambda hrefs: [],
                properties={},
                href="/test",
                resource=resource,
                depth="0",
                strict=True,
            )

            # Parse response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

            # Should have propstat with 404 status for unknown property
            propstats = responses[0].findall("{DAV:}propstat")
            # Find the propstat with 404 status
            found_404 = False
            for propstat in propstats:
                status = propstat.find("{DAV:}status")
                if status is not None and "404" in status.text:
                    found_404 = True
                    break
            self.assertTrue(found_404)

        asyncio.run(run_test())

    def test_report_invalid_href_in_property(self):
        """Test expand-property with property containing invalid href."""

        async def run_test():
            reporter = webdav.ExpandPropertyReporter()

            # Create request body
            body = ET.Element("{DAV:}expand-property")
            prop_el = ET.SubElement(body, "{DAV:}property")
            prop_el.set("name", "{DAV:}owner")
            child_prop_el = ET.SubElement(prop_el, "{DAV:}property")
            child_prop_el.set("name", "{DAV:}displayname")

            # Mock resource with owner pointing to non-existent resource
            resource = Mock()

            class OwnerProperty(webdav.Property):
                name = "{DAV:}owner"

                async def get_value(self, href, resource, el, environ):
                    href_el = ET.SubElement(el, "{DAV:}href")
                    href_el.text = "/principals/nonexistent/"

            properties = {"{DAV:}owner": OwnerProperty()}

            # resources_by_hrefs returns empty (resource not found)
            def resources_by_hrefs(hrefs):
                return []

            response = await reporter.report(
                environ={},
                request_body=body,
                resources_by_hrefs=resources_by_hrefs,
                properties=properties,
                href="/test",
                resource=resource,
                depth="0",
                strict=False,
            )

            # Should complete without error
            self.assertEqual(response.status, 207)

            # Parse response
            xml_content = b"".join(response.body)
            root = ET.fromstring(xml_content)

            responses = root.findall("{DAV:}response")
            self.assertEqual(len(responses), 1)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
