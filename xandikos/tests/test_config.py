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

from ..store.config import CollectionConfig


class CollectionConfigTests(TestCase):

    def test_get_color(self):
        f = StringIO("""\
[DEFAULT]
color = #ffffff
""")
        cc = CollectionConfig.from_file(f)
        self.assertEqual('#ffffff', cc.get_color())

    def test_get_color_missing(self):
        f = StringIO("")
        cc = CollectionConfig.from_file(f)
        self.assertRaises(KeyError, cc.get_color)

    def test_get_comment(self):
        f = StringIO("""\
[DEFAULT]
comment = this is a comment
""")
        cc = CollectionConfig.from_file(f)
        self.assertEqual('this is a comment', cc.get_comment())

    def test_get_comment_missing(self):
        f = StringIO("")
        cc = CollectionConfig.from_file(f)
        self.assertRaises(KeyError, cc.get_comment)

    def test_get_description(self):
        f = StringIO("""\
[DEFAULT]
description = this is a description
""")
        cc = CollectionConfig.from_file(f)
        self.assertEqual('this is a description', cc.get_description())

    def test_get_description_missing(self):
        f = StringIO("")
        cc = CollectionConfig.from_file(f)
        self.assertRaises(KeyError, cc.get_description)

    def test_get_displayname(self):
        f = StringIO("""\
[DEFAULT]
displayname = DISPLAY-NAME
""")
        cc = CollectionConfig.from_file(f)
        self.assertEqual('DISPLAY-NAME', cc.get_displayname())

    def test_get_displayname_missing(self):
        f = StringIO("")
        cc = CollectionConfig.from_file(f)
        self.assertRaises(KeyError, cc.get_displayname)
