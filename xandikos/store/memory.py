# Xandikos
# Copyright (C) 2025 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Memory store implementation."""

import uuid
from collections.abc import Iterable

from . import (
    MIMETYPES,
    DuplicateUidError,
    InvalidETag,
    NoSuchItem,
    Store,
    open_by_content_type,
    open_by_extension,
)
from .index import MemoryIndex


class MemoryStore(Store):
    """Pure in-memory store implementation."""

    def __init__(self, *, check_for_duplicate_uids=True):
        super().__init__(MemoryIndex())
        self._items = {}  # name -> (content_type, data, etag)
        self._etag_counter = 0
        self._check_for_duplicate_uids = check_for_duplicate_uids
        # Maps uids to (name, etag)
        self._uid_to_name = {}
        # Maps names to (etag, uid)
        self._name_to_uid = {}
        self._source_url = None
        self._comment = None
        self._color = None

    def _generate_etag(self) -> str:
        """Generate a unique etag."""
        self._etag_counter += 1
        return f"etag-{self._etag_counter:06d}"

    def _get_raw(self, name: str, etag: str | None = None) -> Iterable[bytes]:
        """Get raw contents of an item."""
        if name not in self._items:
            raise KeyError(name)
        return self._items[name][1]

    def iter_with_etag(self, ctag: str | None = None):
        """Iterate over all items with etag."""
        for name, (content_type, data, etag) in self._items.items():
            yield (name, content_type, etag)

    def _check_duplicate(self, uid, name, replace_etag):
        if uid is not None and self._check_for_duplicate_uids:
            try:
                (existing_name, _) = self._uid_to_name[uid]
            except KeyError:
                pass
            else:
                if existing_name != name:
                    raise DuplicateUidError(uid, existing_name, name)

        try:
            current_etag = self._items[name][2]
        except KeyError:
            current_etag = None
        if replace_etag is not None and current_etag != replace_etag:
            raise InvalidETag(name, current_etag, replace_etag)
        return current_etag

    def import_one(
        self,
        name: str,
        content_type: str,
        data: Iterable[bytes],
        message: str | None = None,
        author: str | None = None,
        replace_etag: str | None = None,
        requester: str | None = None,
    ) -> tuple[str, str]:
        """Import a single item."""
        if content_type is None:
            fi = open_by_extension(data, name, self.extra_file_handlers)
        else:
            fi = open_by_content_type(data, content_type, self.extra_file_handlers)
        if name is None:
            name = str(uuid.uuid4())
            extension = MIMETYPES.guess_extension(content_type)
            if extension is not None:
                name += extension
        fi.validate()
        try:
            uid = fi.get_uid()
        except (KeyError, NotImplementedError):
            uid = None
        self._check_duplicate(uid, name, replace_etag)

        etag = self._generate_etag()
        # Store normalized data
        normalized_data = list(fi.normalized())
        self._items[name] = (content_type, normalized_data, etag)

        # Update UID tracking
        if name in self._name_to_uid:
            old_uid = self._name_to_uid[name][1]
            if old_uid is not None and old_uid in self._uid_to_name:
                del self._uid_to_name[old_uid]

        self._name_to_uid[name] = (etag, uid)
        if uid is not None:
            self._uid_to_name[uid] = (name, etag)

        return (name, etag)

    def delete_one(
        self,
        name: str,
        message: str | None = None,
        author: str | None = None,
        etag: str | None = None,
    ) -> None:
        """Delete an item."""
        if name not in self._items:
            raise NoSuchItem(name)

        if etag is not None:
            current_etag = self._items[name][2]
            if current_etag != etag:
                raise InvalidETag(name, etag, current_etag)

        # Clean up UID tracking
        if name in self._name_to_uid:
            old_uid = self._name_to_uid[name][1]
            if old_uid is not None and old_uid in self._uid_to_name:
                del self._uid_to_name[old_uid]
            del self._name_to_uid[name]

        del self._items[name]

    def get_ctag(self) -> str:
        """Return a ctag representing current state."""
        return f"ctag-{len(self._items)}-{self._etag_counter}"

    def set_type(self, store_type: str) -> None:
        """Set store type (no-op for memory store)."""
        pass

    def set_description(self, description: str) -> None:
        """Set description (no-op for memory store)."""
        pass

    def get_description(self) -> str:
        """Get description."""
        return "Memory Store"

    def get_displayname(self) -> str:
        """Get display name."""
        return "Memory Store"

    def set_displayname(self, displayname: str) -> None:
        """Set display name (no-op for memory store)."""
        pass

    def get_color(self) -> str:
        """Get color."""
        if self._color is None:
            raise KeyError("Color not set")
        return self._color

    def set_color(self, color: str) -> None:
        """Set color (no-op for memory store)."""
        self._color = color

    def iter_changes(self, old_ctag: str, new_ctag: str):
        """Get changes between versions (not implemented for memory store)."""
        raise NotImplementedError(self.iter_changes)

    def get_comment(self) -> str:
        """Get comment."""
        if self._comment is None:
            raise KeyError("Comment not set")
        return self._comment

    def set_comment(self, comment: str) -> None:
        """Set comment (no-op for memory store)."""
        self._comment = comment

    def destroy(self) -> None:
        """Destroy store."""
        self._items.clear()
        self._uid_to_name.clear()
        self._name_to_uid.clear()

    def subdirectories(self):
        """Return subdirectories (empty for memory store)."""
        return []

    def get_source_url(self) -> str:
        """Get source URL."""
        if self._source_url is None:
            raise KeyError("Source URL not set")
        return self._source_url

    def set_source_url(self, url: str) -> None:
        """Set source URL (no-op for memory store)."""
        self._source_url = url
