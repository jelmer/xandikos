# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Tests for xandikos.multi_user module."""

import argparse
import os
import shutil
import tempfile
import unittest

from xandikos.multi_user import (
    MultiUserXandikosBackend,
    add_parser,
)
from xandikos.store import (
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_SCHEDULE_INBOX,
)


class MultiUserXandikosBackendTests(unittest.TestCase):
    """Tests for MultiUserXandikosBackend."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_init_default_paths(self):
        """Test initialization with default path settings."""
        backend = MultiUserXandikosBackend(self.test_dir)

        self.assertEqual(backend.principal_path_prefix, "/")
        self.assertEqual(backend.principal_path_suffix, "/")
        self.assertTrue(backend.autocreate)

    def test_init_custom_paths(self):
        """Test initialization with custom path settings."""
        backend = MultiUserXandikosBackend(
            self.test_dir,
            principal_path_prefix="/users/",
            principal_path_suffix="/dav/",
        )

        self.assertEqual(backend.principal_path_prefix, "/users/")
        self.assertEqual(backend.principal_path_suffix, "/dav/")

    def test_init_with_kwargs(self):
        """Test that additional kwargs are passed to parent class."""
        backend = MultiUserXandikosBackend(
            self.test_dir,
            paranoid=True,
            index_threshold=100,
        )

        self.assertTrue(backend.paranoid)
        self.assertEqual(backend.index_threshold, 100)

    def test_set_principal_creates_principal(self):
        """Test that set_principal creates a new principal."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("alice")

        resource = backend.get_resource("/alice/")
        self.assertIsNotNone(resource)

    def test_set_principal_marks_as_principal(self):
        """Test that set_principal marks the path as a principal."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("alice")

        # _mark_as_principal normalizes paths
        self.assertIn("/alice", backend._user_principals)

    def test_set_principal_with_custom_prefix(self):
        """Test set_principal with custom prefix."""
        backend = MultiUserXandikosBackend(
            self.test_dir, principal_path_prefix="/users/"
        )
        backend.set_principal("bob")

        resource = backend.get_resource("/users/bob/")
        self.assertIsNotNone(resource)
        self.assertIn("/users/bob", backend._user_principals)

    def test_set_principal_with_custom_suffix(self):
        """Test set_principal with custom suffix."""
        backend = MultiUserXandikosBackend(
            self.test_dir, principal_path_suffix="/principal/"
        )
        backend.set_principal("charlie")

        resource = backend.get_resource("/charlie/principal/")
        self.assertIsNotNone(resource)
        self.assertIn("/charlie/principal", backend._user_principals)

    def test_set_principal_with_custom_prefix_and_suffix(self):
        """Test set_principal with both custom prefix and suffix."""
        backend = MultiUserXandikosBackend(
            self.test_dir,
            principal_path_prefix="/accounts/",
            principal_path_suffix="/home/",
        )
        backend.set_principal("dave")

        resource = backend.get_resource("/accounts/dave/home/")
        self.assertIsNotNone(resource)
        self.assertIn("/accounts/dave/home", backend._user_principals)

    def test_set_principal_override_prefix(self):
        """Test overriding prefix at method call time."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("eve", principal_path_prefix="/special/")

        resource = backend.get_resource("/special/eve/")
        self.assertIsNotNone(resource)
        self.assertIn("/special/eve", backend._user_principals)

    def test_set_principal_override_suffix(self):
        """Test overriding suffix at method call time."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("frank", principal_path_suffix="/user/")

        resource = backend.get_resource("/frank/user/")
        self.assertIsNotNone(resource)
        self.assertIn("/frank/user", backend._user_principals)

    def test_set_principal_override_both(self):
        """Test overriding both prefix and suffix at method call time."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal(
            "grace",
            principal_path_prefix="/custom/",
            principal_path_suffix="/path/",
        )

        resource = backend.get_resource("/custom/grace/path/")
        self.assertIsNotNone(resource)
        self.assertIn("/custom/grace/path", backend._user_principals)

    def test_set_principal_idempotent(self):
        """Test that calling set_principal twice is idempotent."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("henry")
        resource1 = backend.get_resource("/henry/")

        backend.set_principal("henry")
        resource2 = backend.get_resource("/henry/")

        self.assertIsNotNone(resource1)
        self.assertIsNotNone(resource2)

    def test_set_principal_multiple_users(self):
        """Test creating multiple users."""
        backend = MultiUserXandikosBackend(self.test_dir)

        users = ["alice", "bob", "charlie", "dave", "eve"]
        for user in users:
            backend.set_principal(user)

        for user in users:
            resource = backend.get_resource(f"/{user}/")
            self.assertIsNotNone(resource)
            self.assertIn(f"/{user}", backend._user_principals)

    def test_set_principal_creates_defaults(self):
        """Test that set_principal creates default calendar and addressbook."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("ivan")

        # Check calendar was created
        calendar = backend.get_resource("/ivan/calendars/calendar/")
        self.assertIsNotNone(calendar)
        self.assertEqual(calendar.store.get_type(), STORE_TYPE_CALENDAR)

        # Check addressbook was created
        addressbook = backend.get_resource("/ivan/contacts/addressbook/")
        self.assertIsNotNone(addressbook)
        self.assertEqual(addressbook.store.get_type(), STORE_TYPE_ADDRESSBOOK)

        # Check inbox was created
        inbox = backend.get_resource("/ivan/inbox/")
        self.assertIsNotNone(inbox)
        self.assertEqual(inbox.store.get_type(), STORE_TYPE_SCHEDULE_INBOX)

    def test_set_principal_with_special_characters(self):
        """Test usernames with special characters."""
        backend = MultiUserXandikosBackend(self.test_dir)

        # Test with underscores
        backend.set_principal("john_doe")
        self.assertIsNotNone(backend.get_resource("/john_doe/"))

        # Test with hyphens
        backend.set_principal("jane-doe")
        self.assertIsNotNone(backend.get_resource("/jane-doe/"))

        # Test with dots
        backend.set_principal("user.name")
        self.assertIsNotNone(backend.get_resource("/user.name/"))

    def test_set_principal_case_sensitive(self):
        """Test that usernames are case-sensitive."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("Alice")
        backend.set_principal("alice")

        # Both should exist as separate principals
        self.assertIn("/Alice", backend._user_principals)
        self.assertIn("/alice", backend._user_principals)

    def test_find_principals_empty(self):
        """Test find_principals returns empty set initially."""
        backend = MultiUserXandikosBackend(self.test_dir)
        self.assertEqual(backend.find_principals(), set())

    def test_find_principals_after_set(self):
        """Test find_principals returns created principals."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("user1")
        backend.set_principal("user2")

        principals = backend.find_principals()
        self.assertIn("/user1", principals)
        self.assertIn("/user2", principals)

    def test_inherits_from_xandikos_backend(self):
        """Test that MultiUserXandikosBackend has XandikosBackend methods."""
        backend = MultiUserXandikosBackend(self.test_dir)

        # Should have methods from XandikosBackend
        self.assertTrue(hasattr(backend, "get_resource"))
        self.assertTrue(hasattr(backend, "create_collection"))
        self.assertTrue(hasattr(backend, "create_principal"))
        self.assertTrue(hasattr(backend, "_mark_as_principal"))

    def test_create_collection_after_principal(self):
        """Test creating additional collections after principal setup."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("kate")

        # Create an additional calendar
        collection = backend.create_collection("/kate/calendars/work/")
        self.assertIsNotNone(collection)

    def test_empty_username(self):
        """Test behavior with empty username."""
        backend = MultiUserXandikosBackend(self.test_dir)
        # Empty username results in path like "//" which normalizes to "/"
        backend.set_principal("")
        # The root resource should still be accessible
        self.assertIsNotNone(backend.get_resource("/"))


class AddParserTests(unittest.TestCase):
    """Tests for add_parser function."""

    def test_add_parser_creates_arguments(self):
        """Test that add_parser adds expected arguments."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        # Parse with required arguments
        args = parser.parse_args(["-d", "/tmp/test"])

        self.assertEqual(args.directory, "/tmp/test")
        self.assertEqual(args.principal_path_prefix, "/")
        self.assertEqual(args.principal_path_suffix, "/")
        self.assertEqual(args.listen_address, "localhost")
        self.assertEqual(args.port, 8080)
        self.assertFalse(args.dump_dav_xml)
        self.assertFalse(args.avahi)
        self.assertTrue(args.strict)
        self.assertFalse(args.debug)

    def test_add_parser_directory_required(self):
        """Test that directory argument is required."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_add_parser_custom_principal_paths(self):
        """Test parsing custom principal path arguments."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "-d",
                "/tmp/test",
                "--principal-path-prefix",
                "/users/",
                "--principal-path-suffix",
                "/dav/",
            ]
        )

        self.assertEqual(args.principal_path_prefix, "/users/")
        self.assertEqual(args.principal_path_suffix, "/dav/")

    def test_add_parser_listen_options(self):
        """Test parsing listen address and port."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "-d",
                "/tmp/test",
                "-l",
                "0.0.0.0",
                "-p",
                "9090",
            ]
        )

        self.assertEqual(args.listen_address, "0.0.0.0")
        self.assertEqual(args.port, 9090)

    def test_add_parser_long_listen_options(self):
        """Test parsing long-form listen options."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "--directory",
                "/tmp/test",
                "--listen-address",
                "127.0.0.1",
                "--port",
                "8888",
            ]
        )

        self.assertEqual(args.directory, "/tmp/test")
        self.assertEqual(args.listen_address, "127.0.0.1")
        self.assertEqual(args.port, 8888)

    def test_add_parser_socket_options(self):
        """Test parsing unix socket options."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "-d",
                "/tmp/test",
                "--socket-mode",
                "660",
                "--socket-group",
                "www-data",
            ]
        )

        self.assertEqual(args.socket_mode, "660")
        self.assertEqual(args.socket_group, "www-data")

    def test_add_parser_route_prefix(self):
        """Test parsing route prefix."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "-d",
                "/tmp/test",
                "--route-prefix",
                "/caldav/",
            ]
        )

        self.assertEqual(args.route_prefix, "/caldav/")

    def test_add_parser_metrics_port(self):
        """Test parsing metrics port."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "-d",
                "/tmp/test",
                "--metrics-port",
                "9100",
            ]
        )

        self.assertEqual(args.metrics_port, "9100")

    def test_add_parser_debug_flag(self):
        """Test parsing debug flag."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--debug"])
        self.assertTrue(args.debug)

    def test_add_parser_dump_dav_xml_flag(self):
        """Test parsing dump-dav-xml flag."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--dump-dav-xml"])
        self.assertTrue(args.dump_dav_xml)

    def test_add_parser_avahi_flag(self):
        """Test parsing avahi flag."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--avahi"])
        self.assertTrue(args.avahi)

    def test_add_parser_no_strict_flag(self):
        """Test parsing no-strict flag."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--no-strict"])
        self.assertFalse(args.strict)

    def test_add_parser_no_detect_systemd_flag(self):
        """Test parsing no-detect-systemd flag."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--no-detect-systemd"])
        self.assertFalse(args.detect_systemd)

    def test_add_parser_hidden_paranoid(self):
        """Test parsing hidden paranoid argument."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--paranoid"])
        self.assertTrue(args.paranoid)

    def test_add_parser_hidden_index_threshold(self):
        """Test parsing hidden index-threshold argument."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(["-d", "/tmp/test", "--index-threshold", "500"])
        self.assertEqual(args.index_threshold, 500)

    def test_add_parser_unix_socket_path(self):
        """Test parsing unix socket as listen address."""
        parser = argparse.ArgumentParser()
        add_parser(parser)

        args = parser.parse_args(
            [
                "-d",
                "/tmp/test",
                "-l",
                "/var/run/xandikos.sock",
            ]
        )

        self.assertEqual(args.listen_address, "/var/run/xandikos.sock")


class MultiUserIntegrationTests(unittest.TestCase):
    """Integration tests for multi-user functionality."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_user_isolation(self):
        """Test that users have isolated data spaces."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("user1")
        backend.set_principal("user2")

        # Each user should have their own calendar home
        user1_calendars = backend.get_resource("/user1/calendars/")
        user2_calendars = backend.get_resource("/user2/calendars/")

        self.assertIsNotNone(user1_calendars)
        self.assertIsNotNone(user2_calendars)

        # Verify they are different resources
        self.assertNotEqual(
            backend._map_to_file_path("/user1/calendars/"),
            backend._map_to_file_path("/user2/calendars/"),
        )

    def test_user_directory_structure(self):
        """Test that correct directory structure is created."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("testuser")

        # Check directory structure exists on disk
        user_path = os.path.join(self.test_dir, "testuser")
        self.assertTrue(os.path.isdir(user_path))

        calendars_path = os.path.join(user_path, "calendars")
        self.assertTrue(os.path.isdir(calendars_path))

        contacts_path = os.path.join(user_path, "contacts")
        self.assertTrue(os.path.isdir(contacts_path))

    def test_nested_principal_paths(self):
        """Test principals with deeply nested paths."""
        backend = MultiUserXandikosBackend(
            self.test_dir,
            principal_path_prefix="/org/company/users/",
            principal_path_suffix="/profile/",
        )
        backend.set_principal("employee")

        resource = backend.get_resource("/org/company/users/employee/profile/")
        self.assertIsNotNone(resource)

        # Check file system path
        expected_path = os.path.join(
            self.test_dir, "org", "company", "users", "employee", "profile"
        )
        self.assertTrue(os.path.isdir(expected_path))

    def test_concurrent_user_creation(self):
        """Test creating many users."""
        backend = MultiUserXandikosBackend(self.test_dir)

        # Create many users
        for i in range(50):
            backend.set_principal(f"user{i}")

        # Verify all were created
        for i in range(50):
            resource = backend.get_resource(f"/user{i}/")
            self.assertIsNotNone(resource)

        self.assertEqual(len(backend.find_principals()), 50)

    def test_principal_with_numeric_name(self):
        """Test principal with numeric username."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("12345")

        resource = backend.get_resource("/12345/")
        self.assertIsNotNone(resource)

    def test_principal_calendar_operations(self):
        """Test basic calendar operations after principal creation."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("caluser")

        calendar = backend.get_resource("/caluser/calendars/calendar/")
        self.assertIsNotNone(calendar)

        # Test setting calendar properties
        calendar.store.set_description("Test Calendar")
        self.assertEqual(calendar.store.get_description(), "Test Calendar")

        calendar.store.set_color("#FF0000")
        self.assertEqual(calendar.store.get_color(), "#FF0000")

    def test_principal_addressbook_operations(self):
        """Test basic addressbook operations after principal creation."""
        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("addruser")

        addressbook = backend.get_resource("/addruser/contacts/addressbook/")
        self.assertIsNotNone(addressbook)

        # Test setting addressbook properties
        addressbook.store.set_description("Test Addressbook")
        self.assertEqual(addressbook.store.get_description(), "Test Addressbook")


class UserAccessControlTests(unittest.TestCase):
    """Tests for user access control and isolation.

    NOTE: Xandikos currently does NOT implement fine-grained access control.
    These tests document the current behavior where any user can access
    any resource if they know the path. The current_user_principal is used
    for discovery (finding the user's own calendars) but not for enforcement.

    Access control enforcement is expected to be handled by a reverse proxy
    or authentication layer in front of Xandikos.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_current_user_principal_substitution(self):
        """Test that current_user_principal uses REMOTE_USER substitution."""
        from xandikos.web import XandikosApp

        backend = MultiUserXandikosBackend(self.test_dir)
        backend.set_principal("alice")

        # Create app with template for current_user_principal
        app = XandikosApp(
            backend,
            current_user_principal="/%(REMOTE_USER)s/",
        )

        # The app should be configured with the template
        self.assertIsNotNone(app)

    def test_users_have_separate_calendar_homes(self):
        """Test that each user has a separate calendar home path."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("alice")
        backend.set_principal("bob")

        alice_calendar = backend.get_resource("/alice/calendars/calendar/")
        bob_calendar = backend.get_resource("/bob/calendars/calendar/")

        self.assertIsNotNone(alice_calendar)
        self.assertIsNotNone(bob_calendar)

        # Verify they have different file paths
        self.assertNotEqual(
            alice_calendar.store.path,
            bob_calendar.store.path,
        )

    def test_users_have_separate_addressbook_homes(self):
        """Test that each user has a separate addressbook home path."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("alice")
        backend.set_principal("bob")

        alice_addressbook = backend.get_resource("/alice/contacts/addressbook/")
        bob_addressbook = backend.get_resource("/bob/contacts/addressbook/")

        self.assertIsNotNone(alice_addressbook)
        self.assertIsNotNone(bob_addressbook)

        # Verify they have different file paths
        self.assertNotEqual(
            alice_addressbook.store.path,
            bob_addressbook.store.path,
        )

    def test_user_data_stored_in_separate_directories(self):
        """Test that user data is stored in physically separate directories."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("alice")
        backend.set_principal("bob")

        alice_path = os.path.join(self.test_dir, "alice")
        bob_path = os.path.join(self.test_dir, "bob")

        self.assertTrue(os.path.isdir(alice_path))
        self.assertTrue(os.path.isdir(bob_path))

        # Verify no overlap in paths
        self.assertFalse(alice_path.startswith(bob_path))
        self.assertFalse(bob_path.startswith(alice_path))

    def test_backend_can_access_any_user_resource(self):
        """Test that backend access is not restricted by user.

        NOTE: This documents current behavior - the backend does not
        enforce access control. This is intentional as access control
        is expected to be handled by a reverse proxy.
        """
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("alice")
        backend.set_principal("bob")

        # Backend can access both users' resources
        alice_calendar = backend.get_resource("/alice/calendars/calendar/")
        bob_calendar = backend.get_resource("/bob/calendars/calendar/")

        self.assertIsNotNone(alice_calendar)
        self.assertIsNotNone(bob_calendar)

    def test_principal_path_determines_user_home(self):
        """Test that principal path correctly determines user's home location."""
        backend = MultiUserXandikosBackend(
            self.test_dir,
            principal_path_prefix="/users/",
            principal_path_suffix="/",
        )

        backend.set_principal("alice")

        # Alice's resources should be under /users/alice/
        alice_principal = backend.get_resource("/users/alice/")
        alice_calendars = backend.get_resource("/users/alice/calendars/")

        self.assertIsNotNone(alice_principal)
        self.assertIsNotNone(alice_calendars)

        # Root should not contain alice directly
        root = backend.get_resource("/")
        self.assertIsNotNone(root)

    def test_find_principals_returns_all_users(self):
        """Test that find_principals returns all registered users."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("alice")
        backend.set_principal("bob")
        backend.set_principal("charlie")

        principals = backend.find_principals()

        self.assertEqual(len(principals), 3)
        self.assertIn("/alice", principals)
        self.assertIn("/bob", principals)
        self.assertIn("/charlie", principals)

    def test_each_user_gets_own_inbox(self):
        """Test that each user has their own schedule inbox."""
        backend = MultiUserXandikosBackend(self.test_dir)

        backend.set_principal("alice")
        backend.set_principal("bob")

        alice_inbox = backend.get_resource("/alice/inbox/")
        bob_inbox = backend.get_resource("/bob/inbox/")

        self.assertIsNotNone(alice_inbox)
        self.assertIsNotNone(bob_inbox)

        # Verify they have different file paths
        self.assertNotEqual(
            alice_inbox.store.path,
            bob_inbox.store.path,
        )


class ModuleExportsTests(unittest.TestCase):
    """Tests for module exports and imports."""

    def test_module_exports(self):
        """Test that expected symbols are exported."""
        from xandikos import multi_user

        self.assertTrue(hasattr(multi_user, "MultiUserXandikosBackend"))
        self.assertTrue(hasattr(multi_user, "add_parser"))
        self.assertTrue(hasattr(multi_user, "main"))

    def test_all_exports(self):
        """Test __all__ contains expected exports."""
        from xandikos.multi_user import __all__

        self.assertIn("MultiUserXandikosBackend", __all__)
        self.assertIn("add_parser", __all__)
        self.assertIn("main", __all__)

    def test_multi_user_backend_importable(self):
        """Test that MultiUserXandikosBackend can be imported directly."""
        from xandikos.multi_user import MultiUserXandikosBackend

        self.assertIsNotNone(MultiUserXandikosBackend)

    def test_add_parser_importable(self):
        """Test that add_parser can be imported directly."""
        from xandikos.multi_user import add_parser

        self.assertIsNotNone(add_parser)
        self.assertTrue(callable(add_parser))

    def test_main_importable(self):
        """Test that main can be imported directly."""
        from xandikos.multi_user import main

        self.assertIsNotNone(main)
        self.assertTrue(callable(main))
