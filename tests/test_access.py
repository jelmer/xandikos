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

"""Tests for xandikos.access (RFC 3744 WebDAV ACL)."""

import asyncio
import unittest

from xandikos import access, webdav
from xandikos.webdav import ET


class CurrentUserPrivilegeSetPropertyTests(unittest.TestCase):
    """Tests for CurrentUserPrivilegeSetProperty (RFC 3744 Section 3.7)."""

    def test_property_name(self):
        """Test current-user-privilege-set property name."""
        prop = access.CurrentUserPrivilegeSetProperty()
        self.assertEqual(prop.name, "{DAV:}current-user-privilege-set")

    def test_property_attributes(self):
        """Test current-user-privilege-set property attributes.

        RFC 3744 Section 3.7: This is a protected property that
        identifies the privileges granted to the current user.
        """
        prop = access.CurrentUserPrivilegeSetProperty()
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)

    def test_get_value(self):
        """Test current-user-privilege-set get_value method.

        RFC 3744 Section 3.7: Contains the privileges currently
        granted to the authenticated user.
        """

        async def run_test():
            prop = access.CurrentUserPrivilegeSetProperty()

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/test", resource, el, {})

            # Should have a privilege element
            privileges = el.findall("{DAV:}privilege")
            self.assertEqual(len(privileges), 1)

            # Should contain DAV:all privilege (current implementation)
            all_priv = privileges[0].find("{DAV:}all")
            self.assertIsNotNone(all_priv)

        asyncio.run(run_test())

    def test_get_value_xml_structure(self):
        """Test that current-user-privilege-set generates correct XML structure."""

        async def run_test():
            prop = access.CurrentUserPrivilegeSetProperty()

            class MockResource:
                pass

            resource = MockResource()
            el = ET.Element("{DAV:}current-user-privilege-set")

            await prop.get_value("/test", resource, el, {})

            # Verify XML structure matches RFC 3744 format
            xml_str = ET.tostring(el, encoding="unicode")
            self.assertIn("<ns0:privilege", xml_str)
            self.assertIn("<ns0:all", xml_str)

        asyncio.run(run_test())


class OwnerPropertyTests(unittest.TestCase):
    """Tests for OwnerProperty (RFC 3744 Section 5.1)."""

    def test_property_name(self):
        """Test owner property name."""
        prop = access.OwnerProperty()
        self.assertEqual(prop.name, "{DAV:}owner")

    def test_property_attributes(self):
        """Test owner property attributes.

        RFC 3744 Section 5.1: Identifies a resource as the owner
        of the resource.
        """
        prop = access.OwnerProperty()
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)

    def test_get_value_with_owner(self):
        """Test owner property when resource has an owner.

        RFC 3744 Section 5.1: The owner is typically the principal
        who created the resource.
        """

        async def run_test():
            prop = access.OwnerProperty()

            class MockResource:
                def get_owner(self):
                    return "/principals/user1/"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/resource", resource, el, {})

            # Should have an href element with the owner
            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/principals/user1/")

        asyncio.run(run_test())

    def test_get_value_without_owner(self):
        """Test owner property when resource has no owner."""

        async def run_test():
            prop = access.OwnerProperty()

            class MockResource:
                def get_owner(self):
                    return None

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/resource", resource, el, {})

            # Should have no href elements when no owner
            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 0)

        asyncio.run(run_test())

    def test_get_value_with_base_href(self):
        """Test owner property with different base href."""

        async def run_test():
            prop = access.OwnerProperty()

            class MockResource:
                def get_owner(self):
                    return "/principals/admin/"

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/calendars/user1/", resource, el, {})

            # Should have href element
            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            # Should be absolute or relative to base_href
            self.assertIn("/principals/admin/", hrefs[0].text)

        asyncio.run(run_test())


class GroupMembershipPropertyTests(unittest.TestCase):
    """Tests for GroupMembershipProperty (RFC 3744 Section 4.4)."""

    def test_property_name(self):
        """Test group-membership property name."""
        prop = access.GroupMembershipProperty()
        self.assertEqual(prop.name, "{DAV:}group-membership")

    def test_property_attributes(self):
        """Test group-membership property attributes.

        RFC 3744 Section 4.4: Identifies the groups in which the
        principal is a member.
        """
        prop = access.GroupMembershipProperty()
        self.assertFalse(prop.in_allprops)
        self.assertTrue(prop.live)
        self.assertEqual(prop.resource_type, webdav.PRINCIPAL_RESOURCE_TYPE)

    def test_get_value_with_groups(self):
        """Test group-membership with multiple groups.

        RFC 3744 Section 4.4: Lists all groups the principal is member of.
        """

        async def run_test():
            prop = access.GroupMembershipProperty()

            class MockResource:
                def get_group_membership(self):
                    return [
                        "/principals/groups/staff/",
                        "/principals/groups/developers/",
                    ]

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            # Should have two href elements
            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 2)

            # Check both group hrefs are present
            href_texts = [h.text for h in hrefs]
            self.assertIn("/principals/groups/staff/", href_texts)
            self.assertIn("/principals/groups/developers/", href_texts)

        asyncio.run(run_test())

    def test_get_value_no_groups(self):
        """Test group-membership when principal belongs to no groups."""

        async def run_test():
            prop = access.GroupMembershipProperty()

            class MockResource:
                def get_group_membership(self):
                    return []

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            # Should have no href elements
            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 0)

        asyncio.run(run_test())

    def test_get_value_single_group(self):
        """Test group-membership with single group."""

        async def run_test():
            prop = access.GroupMembershipProperty()

            class MockResource:
                def get_group_membership(self):
                    return ["/principals/groups/users/"]

            resource = MockResource()
            el = ET.Element("test")

            await prop.get_value("/principals/user1/", resource, el, {})

            # Should have one href element
            hrefs = el.findall("{DAV:}href")
            self.assertEqual(len(hrefs), 1)
            self.assertEqual(hrefs[0].text, "/principals/groups/users/")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
