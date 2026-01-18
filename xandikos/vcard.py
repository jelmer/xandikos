# Xandikos
# Copyright (C) 2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""VCard file handling."""

import vobject

from . import collation as _mod_collation
from .store import File, Filter, InvalidFileContents
from .store.index import IndexDict, IndexKey, IndexValueIterator


class VCardFile(File):
    content_type = "text/vcard"

    def __init__(self, content, content_type) -> None:
        super().__init__(content, content_type)
        self._addressbook = None

    def validate(self):
        c = b"".join(self.content).strip()
        # TODO(jelmer): Do more extensive checking of VCards
        if not c.startswith((b"BEGIN:VCARD\r\n", b"BEGIN:VCARD\n")) or not c.endswith(
            b"\nEND:VCARD"
        ):
            raise InvalidFileContents(
                self.content_type,
                self.content,
                "Missing header and trailer lines",
            )
        if not self.addressbook.validate():
            # TODO(jelmer): Get data about what is invalid
            raise InvalidFileContents(
                self.content_type, self.content, "Invalid VCard file"
            )

    @property
    def addressbook(self):
        if self._addressbook is None:
            text = b"".join(self.content).decode("utf-8", "surrogateescape")
            try:
                self._addressbook = vobject.readOne(text)
            except vobject.base.ParseError as exc:
                raise InvalidFileContents(
                    self.content_type, self.content, str(exc)
                ) from exc
        return self._addressbook

    def _get_index(self, key: IndexKey) -> IndexValueIterator:
        """Extract index values from a vCard file.

        Index keys follow patterns like:
        - P=FN for properties (e.g., FN, N, EMAIL, TEL)
        """
        segments = key.split("/")
        if segments[0].startswith("P="):
            prop_name = segments[0][2:].upper()

            # Iterate through all children to get all instances of a property
            for child in self.addressbook.getChildren():
                if child.name.upper() == prop_name:
                    if hasattr(child, "value") and child.value is not None:
                        value = child.value
                        if isinstance(value, str):
                            yield value.encode("utf-8")
                        elif isinstance(value, list):
                            # For structured properties like ORG, yield the full value
                            # CardDAV text-match should match against any component
                            for component in value:
                                if component:
                                    yield component.encode("utf-8")
                        else:
                            # For other types, convert to string
                            yield str(value).encode("utf-8")


def get_vcard_properties(vcard, prop_name):
    """Get all instances of a property from a vCard.

    Args:
        vcard: vobject vCard object
        prop_name: Property name (case-insensitive)

    Returns:
        List of property objects
    """
    prop_name = prop_name.upper()
    properties = []
    for child in vcard.getChildren():
        if child.name.upper() == prop_name:
            properties.append(child)
    return properties


class TextMatch:
    """Text matching for vCard properties."""

    def __init__(
        self,
        text: str,
        collation: str = "i;unicode-casemap",
        negate_condition: bool = False,
        match_type: str = "contains",
    ):
        self.text = text
        self.collation = _mod_collation.get_collation(collation)
        self.negate_condition = negate_condition
        self.match_type = match_type

    def match(self, value: str) -> bool:
        """Check if a value matches this text match."""
        # Convert both to uppercase for case-insensitive comparison
        text_upper = self.text.upper()
        value_upper = value.upper()

        if self.match_type == "equals":
            result = self.collation(self.text, value, "equals")
        elif self.match_type == "contains":
            # Bypass collation for contains since it's implemented incorrectly
            result = text_upper in value_upper
        elif self.match_type == "starts-with":
            result = value_upper.startswith(text_upper)
        elif self.match_type == "ends-with":
            result = value_upper.endswith(text_upper)
        else:
            result = False

        return not result if self.negate_condition else result


class ParamFilter:
    """Parameter filter for vCard properties."""

    def __init__(self, name: str, is_not_defined: bool = False):
        self.name = name.upper()
        self.is_not_defined = is_not_defined
        self.text_match: TextMatch | None = None

    def add_text_match(
        self,
        text: str,
        collation: str = "i;unicode-casemap",
        negate_condition: bool = False,
        match_type: str = "contains",
    ) -> TextMatch:
        """Add a text match to this parameter filter."""
        self.text_match = TextMatch(text, collation, negate_condition, match_type)
        return self.text_match

    def match(self, prop) -> bool:
        """Check if a property matches this parameter filter."""
        params = getattr(prop, "params", {})

        if self.is_not_defined:
            return self.name not in params

        if self.name not in params:
            return False

        if self.text_match:
            param_value = params[self.name]
            # vCard parameters can be lists or strings
            if isinstance(param_value, list):
                # Check if any value in the list matches
                for val in param_value:
                    if self.text_match.match(str(val)):
                        return True
                return False
            else:
                return self.text_match.match(str(param_value))

        return True


class PropertyFilter:
    """Property filter for vCard queries."""

    def __init__(self, name: str, is_not_defined: bool = False):
        self.name = name.upper()
        self.is_not_defined = is_not_defined
        self.text_matches: list[TextMatch] = []
        self.param_filters: list[ParamFilter] = []

    def add_text_match(
        self,
        text: str,
        collation: str = "i;unicode-casemap",
        negate_condition: bool = False,
        match_type: str = "contains",
    ) -> TextMatch:
        """Add a text match to this property filter."""
        tm = TextMatch(text, collation, negate_condition, match_type)
        self.text_matches.append(tm)
        return tm

    def add_param_filter(self, name: str, is_not_defined: bool = False) -> ParamFilter:
        """Add a parameter filter to this property filter."""
        pf = ParamFilter(name, is_not_defined)
        self.param_filters.append(pf)
        return pf

    def match(self, vcard) -> bool:
        """Check if a vCard matches this property filter."""
        properties = get_vcard_properties(vcard, self.name)

        if self.is_not_defined:
            return len(properties) == 0

        if not properties:
            return False

        # If no specific filters, just check existence
        if not self.text_matches and not self.param_filters:
            return True

        # Check if any property instance matches all criteria
        for prop in properties:
            prop_matches = True

            # Check text matches
            for text_match in self.text_matches:
                value = str(prop.value) if hasattr(prop, "value") else str(prop)
                if not text_match.match(value):
                    prop_matches = False
                    break

            # Check param filters
            if prop_matches:
                for param_filter in self.param_filters:
                    if not param_filter.match(prop):
                        prop_matches = False
                        break

            if prop_matches:
                return True

        return False

    def match_indexes(self, indexes: IndexDict) -> bool:
        """Check if indexed values match this property filter."""
        index_key = f"P={self.name}"

        if self.is_not_defined:
            return index_key not in indexes or not indexes.get(index_key)

        values = indexes.get(index_key, [])
        if not values:
            return False

        # If no specific filters, just check existence
        if not self.text_matches:
            return True

        # Check if any indexed value matches all text criteria
        for value in values:
            if isinstance(value, bytes):
                str_value = value.decode("utf-8", "replace")
            else:
                str_value = str(value)

            value_matches = True
            for text_match in self.text_matches:
                if not text_match.match(str_value):
                    value_matches = False
                    break

            if value_matches:
                return True

        return False


class CardDAVFilter(Filter):
    """A filter that works on vCard files."""

    content_type = "text/vcard"

    def __init__(self) -> None:
        self.property_filters: list[PropertyFilter] = []
        self.test = any  # default test mode is "anyof"

    def add_property_filter(
        self, name: str, is_not_defined: bool = False
    ) -> PropertyFilter:
        """Add a property filter."""
        pf = PropertyFilter(name, is_not_defined)
        self.property_filters.append(pf)
        return pf

    def check(self, name: str, file: File) -> bool:
        if not isinstance(file, VCardFile):
            return False

        vcard = file.addressbook
        if vcard is None:
            return False

        results = []
        for prop_filter in self.property_filters:
            results.append(prop_filter.match(vcard))

        return self.test(results) if results else True

    def check_from_indexes(self, name: str, indexes: IndexDict) -> bool:
        """Check from indexes whether a resource matches."""
        results = []

        for prop_filter in self.property_filters:
            results.append(prop_filter.match_indexes(indexes))

        return self.test(results) if results else True

    def index_keys(self) -> list[list[str]]:
        """Return the index keys needed for this filter."""
        result = []
        for prop_filter in self.property_filters:
            if not prop_filter.is_not_defined:
                result.append([f"P={prop_filter.name}"])
        return result


def parse_filter(filter_el, cls):
    """Parse a CardDAV filter element and build a filter object."""
    if filter_el is None:
        return cls

    test_name = filter_el.get("test", "anyof")
    cls.test = {"allof": all, "anyof": any}[test_name]

    for prop_el in filter_el:
        if prop_el.tag == "{urn:ietf:params:xml:ns:carddav}prop-filter":
            parse_prop_filter(prop_el, cls)
        else:
            raise AssertionError(f"unknown filter tag {prop_el.tag!r}")

    return cls


def parse_prop_filter(prop_el, filter_obj):
    """Parse a prop-filter element and add it to the filter."""
    name = prop_el.get("name")
    is_not_defined = False

    # Check for is-not-defined first
    for subel in prop_el:
        if subel.tag == "{urn:ietf:params:xml:ns:carddav}is-not-defined":
            is_not_defined = True
            break

    prop_filter = filter_obj.add_property_filter(name, is_not_defined)

    # Parse sub-elements
    for subel in prop_el:
        if subel.tag == "{urn:ietf:params:xml:ns:carddav}is-not-defined":
            # Already handled
            pass
        elif subel.tag == "{urn:ietf:params:xml:ns:carddav}text-match":
            prop_filter.add_text_match(
                text=subel.text or "",
                collation=subel.get("collation", "i;unicode-casemap"),
                negate_condition=subel.get("negate-condition", "no") == "yes",
                match_type=subel.get("match-type", "contains"),
            )
        elif subel.tag == "{urn:ietf:params:xml:ns:carddav}param-filter":
            parse_param_filter(subel, prop_filter)


def parse_param_filter(param_el, prop_filter):
    """Parse a param-filter element and add it to the property filter."""
    name = param_el.get("name")
    is_not_defined = False

    # Check for is-not-defined first
    for subel in param_el:
        if subel.tag == "{urn:ietf:params:xml:ns:carddav}is-not-defined":
            is_not_defined = True
            break

    param_filter = prop_filter.add_param_filter(name, is_not_defined)

    # Parse text-match if present
    for subel in param_el:
        if subel.tag == "{urn:ietf:params:xml:ns:carddav}text-match":
            param_filter.add_text_match(
                text=subel.text or "",
                collation=subel.get("collation", "i;unicode-casemap"),
                negate_condition=subel.get("negate-condition", "no") == "yes",
                match_type=subel.get("match-type", "contains"),
            )
