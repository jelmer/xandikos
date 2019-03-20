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

"""Collations."""


class UnknownCollation(Exception):

    def __init__(self, collation):
        super(UnknownCollation, self).__init__(
            "Collation %r is not supported" % collation)
        self.collation = collation


collations = {
    'i;ascii-casemap': lambda a, b: (a.decode('ascii').upper() ==
                                     b.decode('ascii').upper()),
    'i;octet': lambda a, b: a == b,
}


def get_collation(name):
    """Get a collation by name.

    :param name: Collation name
    :raises UnknownCollation: If the collation is not supported
    """
    try:
        return collations[name]
    except KeyError:
        raise UnknownCollation(name)
