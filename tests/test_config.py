# Xandikos
# Copyright (C) 2018 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Tests for xandikos.store.config."""

from io import StringIO
from unittest import TestCase

import dulwich.repo

from xandikos.store.config import FileBasedCollectionMetadata, is_metadata_file
from xandikos.store.git import RepoCollectionMetadata


class FileBasedCollectionMetadataTests(TestCase):
    def test_get_color(self):
        f = StringIO(
            """\
[DEFAULT]
color = #ffffff
"""
        )
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual("#ffffff", cc.get_color())

    def test_get_color_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_color)

    def test_get_comment(self):
        f = StringIO(
            """\
[DEFAULT]
comment = this is a comment
"""
        )
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual("this is a comment", cc.get_comment())

    def test_get_comment_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_comment)

    def test_get_description(self):
        f = StringIO(
            """\
[DEFAULT]
description = this is a description
"""
        )
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual("this is a description", cc.get_description())

    def test_get_description_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_description)

    def test_get_displayname(self):
        f = StringIO(
            """\
[DEFAULT]
displayname = DISPLAY-NAME
"""
        )
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual("DISPLAY-NAME", cc.get_displayname())

    def test_get_displayname_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_displayname)


class MetadataTests:
    def test_color(self):
        self.assertRaises(KeyError, self._config.get_color)
        self._config.set_color("#ffffff")
        self.assertEqual("#ffffff", self._config.get_color())
        self._config.set_color(None)
        self.assertRaises(KeyError, self._config.get_color)

    def test_comment(self):
        self.assertRaises(KeyError, self._config.get_comment)
        self._config.set_comment("this is a comment")
        self.assertEqual("this is a comment", self._config.get_comment())
        self._config.set_comment(None)
        self.assertRaises(KeyError, self._config.get_comment)

    def test_displayname(self):
        self.assertRaises(KeyError, self._config.get_displayname)
        self._config.set_displayname("DiSpLaYName")
        self.assertEqual("DiSpLaYName", self._config.get_displayname())
        self._config.set_displayname(None)
        self.assertRaises(KeyError, self._config.get_displayname)

    def test_description(self):
        self.assertRaises(KeyError, self._config.get_description)
        self._config.set_description("this is a description")
        self.assertEqual("this is a description", self._config.get_description())
        self._config.set_description(None)
        self.assertRaises(KeyError, self._config.get_description)

    def test_order(self):
        self.assertRaises(KeyError, self._config.get_order)
        self._config.set_order("this is a order")
        self.assertEqual("this is a order", self._config.get_order())
        self._config.set_order(None)
        self.assertRaises(KeyError, self._config.get_order)

    def test_refreshrate(self):
        self.assertRaises(KeyError, self._config.get_refreshrate)
        self._config.set_refreshrate("PT1H")
        self.assertEqual("PT1H", self._config.get_refreshrate())
        self._config.set_refreshrate(None)
        self.assertRaises(KeyError, self._config.get_refreshrate)

    def test_timezone(self):
        self.assertRaises(KeyError, self._config.get_timezone)
        tz_data = "BEGIN:VTIMEZONE\r\nTZID:America/New_York\r\nEND:VTIMEZONE"
        self._config.set_timezone(tz_data)
        self.assertEqual(tz_data, self._config.get_timezone())
        self._config.set_timezone(None)
        self.assertRaises(KeyError, self._config.get_timezone)


class FileMetadataTests(TestCase, MetadataTests):
    def setUp(self):
        super().setUp()
        self._config = FileBasedCollectionMetadata()


class RepoMetadataTests(TestCase, MetadataTests):
    def setUp(self):
        super().setUp()
        self._repo = dulwich.repo.MemoryRepo()
        self._repo._autogc_disabled = True
        self._config = RepoCollectionMetadata(self._repo)


class IsMetadataFileTests(TestCase):
    """Test the is_metadata_file() helper function."""

    def test_old_config_file_detected(self):
        """Test that the old .xandikos config file is detected as metadata."""
        self.assertTrue(is_metadata_file(".xandikos"))

    def test_new_metadata_directory_detected(self):
        """Test that the new .xandikos metadata directory is detected."""
        self.assertTrue(is_metadata_file(".xandikos"))

    def test_regular_files_not_detected(self):
        """Test that regular files are not detected as metadata files."""
        self.assertFalse(is_metadata_file("event.ics"))
        self.assertFalse(is_metadata_file("calendar.ics"))
        self.assertFalse(is_metadata_file("todo.ics"))
        self.assertFalse(is_metadata_file("README.md"))
        self.assertFalse(is_metadata_file("config.txt"))

    def test_metadata_subdirectory_files_detected(self):
        """Test that files within .xandikos/ metadata directory are detected."""
        self.assertTrue(is_metadata_file(".xandikos/config"))
        self.assertTrue(is_metadata_file(".xandikos/availability.ics"))
        self.assertTrue(is_metadata_file(".xandikos/any-other-file.txt"))

    def test_similar_names_not_detected(self):
        """Test that similar but different names are not detected as metadata files."""
        self.assertFalse(is_metadata_file("xandikos"))
        self.assertFalse(is_metadata_file(".xandikos.bak"))
        self.assertFalse(is_metadata_file(".xandikos_backup"))
        self.assertFalse(is_metadata_file("my.xandikos"))
        self.assertFalse(is_metadata_file(".xandikos.bak/config"))
        self.assertFalse(is_metadata_file("something/.xandikos/config"))

    def test_empty_string_not_detected(self):
        """Test that empty string is not detected as a metadata file."""
        self.assertFalse(is_metadata_file(""))

    def test_case_sensitivity(self):
        """Test that the function is case sensitive."""
        self.assertFalse(is_metadata_file(".XANDIKOS"))
        self.assertFalse(is_metadata_file(".Xandikos"))
        self.assertFalse(is_metadata_file(".XandikoS"))
