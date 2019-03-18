# Xandikos
# Copyright (C) 2019 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Indexing.
"""


class Index(object):
    """Index management."""

    def available_keys(self):
        """Return list of available index keys."""
        raise NotImplementedError(self.available_indexes)

    def get_values(self, name, etag, keys):
        """Get the values for specified keys for a name."""
        raise NotImplementedError(self.get_values)


class MemoryIndex(Index):

    def __init__(self):
        self._indexes = {}
        self._in_index = set()

    def available_keys(self):
        return self._indexes.keys()

    def get_values(self, name, etag, keys):
        if etag not in self._in_index:
            raise KeyError(etag)
        indexes = {}
        for k in keys:
            try:
                indexes[k] = self._indexes[k][etag]
            except KeyError:
                return None
        return indexes

    def add_values(self, name, etag, values):
        for k, v in values.items():
            self._indexes[k][etag] = v
        self._in_index.add(etag)
