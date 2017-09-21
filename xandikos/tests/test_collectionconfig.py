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

import configparser
import unittest

from xandikos.store.config import CollectionConfig


class CollectionConfigTest(unittest.TestCase):

    def test_get_color(self):
        cp = configparser.ConfigParser()
        c = CollectionConfig(cp)
        self.assertRaises(KeyError, c.get_color)
        cp['DEFAULT']['color'] = '040404'
        self.assertEqual('040404', c.get_color())

    def test_get_comment(self):
        cp = configparser.ConfigParser()
        c = CollectionConfig(cp)
        self.assertRaises(KeyError, c.get_comment)
        cp['DEFAULT']['comment'] = 'foo'
        self.assertEqual('foo', c.get_comment())

    def test_get_displayname(self):
        cp = configparser.ConfigParser()
        c = CollectionConfig(cp)
        self.assertRaises(KeyError, c.get_displayname)
        cp['DEFAULT']['displayname'] = 'foo'
        self.assertEqual('foo', c.get_displayname())

    def test_get_description(self):
        cp = configparser.ConfigParser()
        c = CollectionConfig(cp)
        self.assertRaises(KeyError, c.get_description)
        cp['DEFAULT']['description'] = 'foo'
        self.assertEqual('foo', c.get_description())
