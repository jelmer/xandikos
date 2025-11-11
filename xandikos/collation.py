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

from collections.abc import Callable


class UnknownCollation(Exception):
    def __init__(self, collation: str) -> None:
        super().__init__(f"Collation {collation!r} is not supported")
        self.collation = collation


def _match(a, b, k):
    if k == "equals":
        return a == b
    elif k == "contains":
        return b in a
    elif k == "starts-with":
        return a.startswith(b)
    elif k == "ends-with":
        return a.endswith(b)
    else:
        raise NotImplementedError


collations: dict[str, Callable[[str, str, str], bool]] = {
    "i;ascii-casemap": lambda a, b, k: _match(
        a.encode("ascii").upper(), b.encode("ascii").upper(), k
    ),
    "i;octet": lambda a, b, k: _match(a, b, k),
    # TODO(jelmer): Follow all rules as specified in
    # https://datatracker.ietf.org/doc/html/rfc5051
    "i;unicode-casemap": lambda a, b, k: _match(
        a.encode("utf-8", "surrogateescape").upper(),
        b.encode("utf-8", "surrogateescape").upper(),
        k,
    ),
}


def get_collation(name: str) -> Callable[[str, str, str], bool]:
    """Get a collation by name.

    Args:
      name: Collation name
    Raises:
      UnknownCollation: If the collation is not supported
    """
    try:
        return collations[name]
    except KeyError as exc:
        raise UnknownCollation(name) from exc
