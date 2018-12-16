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

"""Collection configuration file.
"""

import configparser

FILENAME = '.xandikos'


class CollectionMetadata(object):
    """Metadata for a configuration."""

    def get_color(self):
        raise NotImplementedError(self.get_color)

    def get_comment(self):
        raise NotImplementedError(self.get_comment)

    def get_displayname(self):
        raise NotImplementedError(self.get_displayname)

    def get_description(self):
        raise NotImplementedError(self.get_description)


class FileBasedCollectionMetadata(CollectionMetadata):
    """Metadata for a configuration."""

    def __init__(self, cp=None):
        if cp is None:
            cp = configparser.ConfigParser()
        self._configparser = cp

    @classmethod
    def from_file(cls, f):
        cp = configparser.ConfigParser()
        cp.read_file(f)
        return cls(cp)

    def get_color(self):
        return self._configparser['DEFAULT']['color']

    def get_comment(self):
        return self._configparser['DEFAULT']['comment']

    def get_displayname(self):
        return self._configparser['DEFAULT']['displayname']

    def get_description(self):
        return self._configparser['DEFAULT']['description']



