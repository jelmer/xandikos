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

"""Tests for xandikos.__main__."""

import asyncio
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from xandikos.__main__ import add_create_collection_parser, create_collection_main, main
from xandikos.store import STORE_TYPE_ADDRESSBOOK, STORE_TYPE_CALENDAR
from xandikos.web import XandikosBackend


class CreateCollectionTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)

    def test_add_create_collection_parser(self):
        """Test that the create-collection parser is correctly configured."""
        import argparse

        parser = argparse.ArgumentParser()
        add_create_collection_parser(parser)

        # Test that required arguments are present
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()  # Suppress argparse error output
        try:
            with self.assertRaises(SystemExit):
                parser.parse_args([])
        finally:
            sys.stderr = old_stderr

        # Test valid arguments
        args = parser.parse_args(
            ["-d", "/test/dir", "--type", "calendar", "--name", "test-cal"]
        )
        self.assertEqual(args.directory, "/test/dir")
        self.assertEqual(args.type, "calendar")
        self.assertEqual(args.name, "test-cal")
        self.assertIsNone(args.displayname)
        self.assertIsNone(args.description)
        self.assertIsNone(args.color)

        # Test with optional arguments
        args = parser.parse_args(
            [
                "-d",
                "/test/dir",
                "--type",
                "addressbook",
                "--name",
                "test-addr",
                "--displayname",
                "Test Address Book",
                "--description",
                "A test address book",
                "--color",
                "#FF0000",
            ]
        )
        self.assertEqual(args.displayname, "Test Address Book")
        self.assertEqual(args.description, "A test address book")
        self.assertEqual(args.color, "#FF0000")

    def test_create_collection_calendar_success(self):
        """Test successful creation of a calendar collection."""
        import argparse

        args = argparse.Namespace(
            directory=self.test_dir,
            type="calendar",
            name="test-calendar",
            displayname="Test Calendar",
            description="A test calendar",
            color="#FF5733",
        )

        result = asyncio.run(create_collection_main(args, None))
        self.assertEqual(result, 0)

        # Verify the collection was created
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "test-calendar")))

        # Verify the collection properties
        backend = XandikosBackend(self.test_dir)
        resource = backend.get_resource("/test-calendar")
        self.assertEqual(resource.store.get_type(), STORE_TYPE_CALENDAR)
        self.assertEqual(resource.store.get_displayname(), "Test Calendar")
        self.assertEqual(resource.store.get_description(), "A test calendar")
        self.assertEqual(resource.store.get_color(), "#FF5733")

    def test_create_collection_addressbook_success(self):
        """Test successful creation of an addressbook collection."""
        import argparse

        args = argparse.Namespace(
            directory=self.test_dir,
            type="addressbook",
            name="test-addressbook",
            displayname="Test Address Book",
            description=None,
            color=None,
        )

        result = asyncio.run(create_collection_main(args, None))
        self.assertEqual(result, 0)

        # Verify the collection was created
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "test-addressbook")))

        # Verify the collection properties
        backend = XandikosBackend(self.test_dir)
        resource = backend.get_resource("/test-addressbook")
        self.assertEqual(resource.store.get_type(), STORE_TYPE_ADDRESSBOOK)
        self.assertEqual(resource.store.get_displayname(), "Test Address Book")

    def test_create_collection_already_exists(self):
        """Test error handling when collection already exists."""
        import argparse

        args = argparse.Namespace(
            directory=self.test_dir,
            type="calendar",
            name="test-calendar",
            displayname=None,
            description=None,
            color=None,
        )

        # Create the collection first time
        result = asyncio.run(create_collection_main(args, None))
        self.assertEqual(result, 0)

        # Try to create again - should fail
        with self.assertLogs("xandikos.__main__", level=logging.ERROR) as cm:
            result = asyncio.run(create_collection_main(args, None))
            self.assertEqual(result, 1)
            self.assertIn("already exists", cm.output[0])

    def test_create_collection_minimal_args(self):
        """Test creating collection with only required arguments."""
        import argparse

        args = argparse.Namespace(
            directory=self.test_dir,
            type="calendar",
            name="minimal-cal",
            displayname=None,
            description=None,
            color=None,
        )

        result = asyncio.run(create_collection_main(args, None))
        self.assertEqual(result, 0)

        # Verify the collection was created
        backend = XandikosBackend(self.test_dir)
        resource = backend.get_resource("/minimal-cal")
        self.assertEqual(resource.store.get_type(), STORE_TYPE_CALENDAR)


class MainCommandTests(unittest.TestCase):
    def test_main_create_collection_subcommand(self):
        """Test that the main function recognizes create-collection subcommand."""
        with tempfile.TemporaryDirectory() as test_dir:
            with self.assertLogs("xandikos.__main__", level=logging.INFO) as cm:
                result = asyncio.run(
                    main(
                        [
                            "create-collection",
                            "-d",
                            test_dir,
                            "--type",
                            "calendar",
                            "--name",
                            "test-cal",
                        ]
                    )
                )
                self.assertEqual(result, 0)
                self.assertIn("Successfully created", cm.output[0])

    def test_main_help_includes_create_collection(self):
        """Test that help includes the create-collection subcommand."""
        import sys
        from io import StringIO

        # Capture stdout since argparse writes help there
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        try:
            with self.assertRaises(SystemExit):
                asyncio.run(main(["--help"]))
        finally:
            sys.stdout = old_stdout

        # Check that help was printed and includes create-collection
        help_output = captured_output.getvalue()
        self.assertIn("create-collection", help_output)

    def test_main_invalid_subcommand(self):
        """Test handling of invalid subcommands."""
        # Note: Due to the default subparser mechanism, unknown commands
        # get passed to the 'serve' subcommand and cause argument errors.
        # This test verifies that the system exits with an error code.
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()  # Suppress argparse error output
        try:
            with patch("builtins.print"):
                with self.assertRaises(SystemExit) as cm:
                    asyncio.run(main(["invalid-command"]))
                # Expect exit code 2 (argparse error)
                self.assertEqual(cm.exception.code, 2)
        finally:
            sys.stderr = old_stderr

    def test_main_create_collection_help(self):
        """Test create-collection subcommand help."""
        import sys
        from io import StringIO

        # Capture stdout since argparse writes help there
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        try:
            with self.assertRaises(SystemExit):
                asyncio.run(main(["create-collection", "--help"]))
        finally:
            sys.stdout = old_stdout

        # Check that help was printed and includes expected options
        help_output = captured_output.getvalue()
        self.assertIn("--type", help_output)
        self.assertIn("--name", help_output)
        self.assertIn("--displayname", help_output)
