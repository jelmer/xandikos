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

from ..store.config import FileBasedCollectionMetadata


class FileBasedCollectionMetadataTests(TestCase):

    def test_get_color(self):
        f = StringIO("""\
[DEFAULT]
color = #ffffff
""")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual('#ffffff', cc.get_color())

    def test_get_color_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_color)

    def test_get_comment(self):
        f = StringIO("""\
[DEFAULT]
comment = this is a comment
""")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual('this is a comment', cc.get_comment())

    def test_get_comment_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_comment)

    def test_get_description(self):
        f = StringIO("""\
[DEFAULT]
description = this is a description
""")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual('this is a description', cc.get_description())

    def test_get_description_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_description)

    def test_get_displayname(self):
        f = StringIO("""\
[DEFAULT]
displayname = DISPLAY-NAME
""")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertEqual('DISPLAY-NAME', cc.get_displayname())

    def test_get_displayname_missing(self):
        f = StringIO("")
        cc = FileBasedCollectionMetadata.from_file(f)
        self.assertRaises(KeyError, cc.get_displayname)


class MetadataTests(object):

    def test_color(self):
        self.assertRaises(KeyError, self._config.get_color)
        self._config.set_color('#ffffff')
        self.assertEqual('#ffffff', self._config.get_color())
        self._config.set_color(None)
        self.assertRaises(KeyError, self._config.get_color)

    def test_comment(self):
        self.assertRaises(KeyError, self._config.get_comment)
        self._config.set_comment('this is a comment')
        self.assertEqual('this is a comment', self._config.get_comment())
        self._config.set_comment(None)
        self.assertRaises(KeyError, self._config.get_comment)

    def test_displayname(self):
        self.assertRaises(KeyError, self._config.get_displayname)
        self._config.set_displayname('DiSpLaYName')
        self.assertEqual('DiSpLaYName', self._config.get_displayname())
        self._config.set_displayname(None)
        self.assertRaises(KeyError, self._config.get_displayname)

    def test_description(self):
        self.assertRaises(KeyError, self._config.get_description)
        self._config.set_description('this is a description')
        self.assertEqual(
            'this is a description', self._config.get_description())
        self._config.set_description(None)
        self.assertRaises(KeyError, self._config.get_description)

    def test_order(self):
        self.assertRaises(KeyError, self._config.get_order)
        self._config.set_order('this is a order')
        self.assertEqual('this is a order', self._config.get_order())
        self._config.set_order(None)
        self.assertRaises(KeyError, self._config.get_order)


class FileMetadataTests(TestCase, MetadataTests):

    def setUp(self):
        super(FileMetadataTests, self).setUp()
        self._config = FileBasedCollectionMetadata()


class RepoMetadataTests(TestCase, MetadataTests):

    def setUp(self):
        super(RepoMetadataTests, self).setUp()
        import dulwich.repo
        from ..store.git import RepoCollectionMetadata
        self._repo = dulwich.repo.MemoryRepo()
        self._config = RepoCollectionMetadata(self._repo)
