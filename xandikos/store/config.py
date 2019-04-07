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
        """Get the color for this collection.
        """
        raise NotImplementedError(self.get_color)

    def set_color(self, color):
        """Change the color of this collection."""
        raise NotImplementedError(self.set_color)

    def get_comment(self):
        raise NotImplementedError(self.get_comment)

    def get_displayname(self):
        raise NotImplementedError(self.get_displayname)

    def get_description(self):
        raise NotImplementedError(self.get_description)

    def get_order(self):
        raise NotImplementedError(self.get_order)

    def set_order(self, order):
        raise NotImplementedError(self.set_order)


class FileBasedCollectionMetadata(CollectionMetadata):
    """Metadata for a configuration."""

    def __init__(self, cp=None, save=None):
        if cp is None:
            cp = configparser.ConfigParser()
        self._configparser = cp
        self._save_cb = save

    def _save(self, message):
        if self._save_cb is None:
            return
        self._save_cb(self._configparser, message)

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

    def set_color(self, color):
        if color is not None:
            self._configparser['DEFAULT']['color'] = color
        else:
            del self._configparser['DEFAULT']['color']
        self._save("Set color.")

    def set_displayname(self, displayname):
        if displayname is not None:
            self._configparser['DEFAULT']['displayname'] = displayname
        else:
            del self._configparser['DEFAULT']['displayname']
        self._save("Set display name.")

    def set_description(self, description):
        if description is not None:
            self._configparser['DEFAULT']['description'] = description
        else:
            del self._configparser['DEFAULT']['description']
        self._save("Set description.")

    def set_comment(self, comment):
        if comment is not None:
            self._configparser['DEFAULT']['comment'] = comment
        else:
            del self._configparser['DEFAULT']['comment']
        self._save("Set comment.")

    def set_type(self, store_type):
        self._configparser['DEFAULT']['type'] = store_type
        self._save("Set collection type.")

    def get_type(self):
        return self._configparser['DEFAULT']['type']

    def get_order(self):
        return self._configparser['calendar']['order']

    def set_order(self, order):
        try:
            self._configparser.add_section('calendar')
        except configparser.DuplicateSectionError:
            pass
        if order is None:
            del self._configparser['calendar']['order']
        else:
            self._configparser['calendar']['order'] = order
