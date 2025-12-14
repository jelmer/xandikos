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

"""Stores and store sets.

ETags (https://en.wikipedia.org/wiki/HTTP_ETag) used in this file
are always strong, and should be returned without wrapping quotes.
"""

import logging
import mimetypes
from collections.abc import Iterable, Iterator
from typing import Optional

from .index import AutoIndexManager, IndexDict, IndexKey, IndexValueIterator

STORE_TYPE_ADDRESSBOOK = "addressbook"
STORE_TYPE_CALENDAR = "calendar"
STORE_TYPE_PRINCIPAL = "principal"
STORE_TYPE_SCHEDULE_INBOX = "schedule-inbox"
STORE_TYPE_SCHEDULE_OUTBOX = "schedule-outbox"
STORE_TYPE_SUBSCRIPTION = "subscription"
STORE_TYPE_OTHER = "other"
VALID_STORE_TYPES = (
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_PRINCIPAL,
    STORE_TYPE_SCHEDULE_INBOX,
    STORE_TYPE_SCHEDULE_OUTBOX,
    STORE_TYPE_SUBSCRIPTION,
    STORE_TYPE_OTHER,
)

MIMETYPES = mimetypes.MimeTypes()
MIMETYPES.add_type("text/calendar", ".ics")  # type: ignore
MIMETYPES.add_type("text/vcard", ".vcf")  # type: ignore

DEFAULT_MIME_TYPE = "application/octet-stream"


class InvalidCTag(Exception):
    """The request CTag can not be retrieved."""

    def __init__(self, ctag) -> None:
        self.ctag = ctag


class File:
    """A file type handler."""

    content: Iterable[bytes]
    content_type: str

    def __init__(self, content: Iterable[bytes], content_type: str) -> None:
        self.content = content
        self.content_type = content_type

    def validate(self) -> None:
        """Verify that file contents are valid.

        :raise InvalidFileContents: Raised if a file is not valid
        """

    def normalized(self) -> Iterable[bytes]:
        """Return a normalized version of the file."""
        return self.content

    def describe(self, name: str) -> str:
        """Describe the contents of this file.

        Used in e.g. commit messages.
        """
        return name

    def get_uid(self) -> str:
        """Return UID.

        :raise NotImplementedError: If UIDs aren't supported for this format
        :raise KeyError: If there is no UID set on this file
        :raise InvalidFileContents: If the file is misformatted
        Returns: UID
        """
        raise NotImplementedError(self.get_uid)

    def describe_delta(self, name: str, previous: Optional["File"]) -> Iterator[str]:
        """Describe the important difference between this and previous one.

        Args:
          name: File name
          previous: Previous file to compare to.

        Raises:
          InvalidFileContents: If the file is misformatted
        Returns: List of strings describing change
        """
        assert name is not None
        item_description = self.describe(name)
        assert item_description is not None
        if previous is None:
            yield "Added " + item_description
        else:
            yield "Modified " + item_description

    def _get_index(self, key: IndexKey) -> IndexValueIterator:
        """Obtain an index for this file.

        Args:
          key: Index key
        Returns:
          iterator over index values
        """
        raise NotImplementedError(self._get_index)

    def get_indexes(self, keys: Iterable[IndexKey]) -> IndexDict:
        """Obtain indexes for this file.

        Args:
          keys: Iterable of index keys
        Returns: Dictionary mapping key names to values
        """
        ret = {}
        for k in keys:
            ret[k] = list(self._get_index(k))
        return ret


class Filter:
    """A filter that can be used to query for certain resources.

    Filters are often resource-type specific.
    """

    content_type: str

    def check(self, name: str, resource: File) -> bool:
        """Check if this filter applies to a resource.

        Args:
          name: Name of the resource
          resource: File object
        Returns: boolean
        """
        raise NotImplementedError(self.check)

    def index_keys(self) -> list[list[IndexKey]]:
        """Returns a list of indexes that could be used to apply this filter.

        Returns: AND-list of OR-options
        """
        raise NotImplementedError(self.index_keys)

    def check_from_indexes(self, name: str, indexes: IndexDict) -> bool:
        """Check from a set of indexes whether a resource matches.

        Args:
          name: Name of the resource
          indexes: Dictionary mapping index names to values
        Returns: boolean
        """
        raise NotImplementedError(self.check_from_indexes)


def open_by_content_type(
    content: Iterable[bytes], content_type: str, extra_file_handlers
) -> File:
    """Open a file based on content type.

    Args:
      content: list of bytestrings with content
      content_type: MIME type
    Returns: File instance
    """
    return extra_file_handlers.get(content_type.split(";")[0], File)(
        content, content_type
    )


def open_by_extension(
    content: Iterable[bytes],
    name: str,
    extra_file_handlers: dict[str, type[File]],
) -> File:
    """Open a file based on the filename extension.

    Args:
      content: list of bytestrings with content
      name: Name of file to open
    Returns: File instance
    """
    (mime_type, _) = MIMETYPES.guess_type(name)
    if mime_type is None:
        mime_type = DEFAULT_MIME_TYPE
    return open_by_content_type(
        content, mime_type, extra_file_handlers=extra_file_handlers
    )


class DuplicateUidError(Exception):
    """UID already exists in store."""

    def __init__(self, uid: str, existing_name: str, new_name: str) -> None:
        self.uid = uid
        self.existing_name = existing_name
        self.new_name = new_name


class NoSuchItem(Exception):
    """No such item."""

    def __init__(self, name: str) -> None:
        self.name = name


class InvalidETag(Exception):
    """Unexpected value for etag."""

    def __init__(self, name: str, expected_etag: str, got_etag: str) -> None:
        self.name = name
        self.expected_etag = expected_etag
        self.got_etag = got_etag


class NotStoreError(Exception):
    """Not a store."""

    def __init__(self, path: str) -> None:
        self.path = path


class InvalidFileContents(Exception):
    """Invalid file contents."""

    def __init__(self, content_type: str, data, error) -> None:
        self.content_type = content_type
        self.data = data
        self.error = error

    def __str__(self) -> str:
        return f"Invalid {self.content_type} file: {self.error}"


class InsufficientIndexDataError(Exception):
    """Raised when index data is insufficient for filtering.

    This indicates that the filter cannot determine whether a resource matches
    based solely on index data, and a full file check is required.
    """

    pass


class OutOfSpaceError(Exception):
    """Out of disk space."""

    def __init__(self) -> None:
        pass


class LockedError(Exception):
    """File or store being accessed is locked."""

    def __init__(self, path: str) -> None:
        self.path = path


class Store:
    """A object store."""

    extra_file_handlers: dict[str, type[File]]

    def __init__(
        self,
        index,
        *,
        double_check_indexes: bool = False,
        index_threshold: int | None = None,
    ) -> None:
        self.extra_file_handlers = {}
        self.index = index
        self.index_manager = AutoIndexManager(self.index, threshold=index_threshold)
        self.double_check_indexes = double_check_indexes

    def load_extra_file_handler(self, file_handler: type[File]) -> None:
        self.extra_file_handlers[file_handler.content_type] = file_handler

    def iter_with_etag(self, ctag: str | None = None) -> Iterator[tuple[str, str, str]]:
        """Iterate over all items in the store with etag.

        Args:
          ctag: Possible ctag to iterate for
        Returns: iterator over (name, content_type, etag) tuples
        """
        raise NotImplementedError(self.iter_with_etag)

    def iter_with_filter(self, filter: Filter) -> Iterator[tuple[str, File, str]]:
        """Iterate over all items in the store that match a particular filter.

        Args:
          filter: Filter to apply
        Returns: iterator over (name, file, etag) tuples
        """
        if self.index_manager is not None:
            try:
                necessary_keys = filter.index_keys()
            except NotImplementedError:
                pass
            else:
                present_keys = self.index_manager.find_present_keys(necessary_keys)
                if present_keys is not None:
                    return self._iter_with_filter_indexes(filter, present_keys)
        return self._iter_with_filter_naive(filter)

    def _iter_with_filter_naive(
        self, filter: Filter
    ) -> Iterator[tuple[str, File, str]]:
        for name, content_type, etag in self.iter_with_etag():
            if not filter.content_type == content_type:
                continue
            file = self.get_file(name, content_type, etag)
            try:
                if filter.check(name, file):
                    yield (name, file, etag)
            except InvalidFileContents:
                logging.warning("Unable to parse file %s, skipping.", name)

    def _iter_with_filter_indexes(
        self, filter: Filter, keys
    ) -> Iterator[tuple[str, File, str]]:
        for name, content_type, etag in self.iter_with_etag():
            if not filter.content_type == content_type:
                continue
            try:
                file_values = self.index.get_values(name, etag, keys)
            except KeyError:
                # Index values not yet present for this file.
                file = self.get_file(name, content_type, etag)
                try:
                    file_values = file.get_indexes(self.index.available_keys())
                except InvalidFileContents:
                    logging.warning(
                        "Unable to parse file %s for indexing, skipping.", name
                    )
                    file_values = {}
                self.index.add_values(name, etag, file_values)
                try:
                    if filter.check_from_indexes(name, file_values):
                        yield (name, file, etag)
                except InsufficientIndexDataError:
                    # Fallback to full file check when index data is insufficient
                    if filter.check(name, file):
                        yield (name, file, etag)
            else:
                if file_values is None:
                    continue
                file = self.get_file(name, content_type, etag)
                if self.double_check_indexes:
                    if file_values != file.get_indexes(keys):
                        raise AssertionError(
                            f"{file_values!r} != {file.get_indexes(keys)!r}"
                        )
                    try:
                        index_result = filter.check_from_indexes(name, file_values)
                        file_result = filter.check(name, file)
                        if index_result != file_result:
                            raise AssertionError(
                                f"index based filter {filter} "
                                f"(values: {file_values}) not matching "
                                "real file filter"
                            )
                    except InsufficientIndexDataError:
                        # Index data insufficient - this is expected in some cases
                        pass
                try:
                    if filter.check_from_indexes(name, file_values):
                        file = self.get_file(name, content_type, etag)
                        yield (name, file, etag)
                except InsufficientIndexDataError:
                    # Fallback to full file check when index data is insufficient
                    if filter.check(name, file):
                        yield (name, file, etag)

    def get_file(
        self,
        name: str,
        content_type: str | None = None,
        etag: str | None = None,
    ) -> File:
        """Get the contents of an object.

        Returns: A File object
        """
        if content_type is None:
            return open_by_extension(
                self._get_raw(name, etag),
                name,
                extra_file_handlers=self.extra_file_handlers,
            )
        else:
            return open_by_content_type(
                self._get_raw(name, etag),
                content_type,
                extra_file_handlers=self.extra_file_handlers,
            )

    def _get_raw(self, name: str, etag: str | None = None) -> Iterable[bytes]:
        """Get the raw contents of an object.

        Args:
          name: Filename
          etag: Optional etag to return
        Returns: raw contents
        """
        raise NotImplementedError(self._get_raw)

    def get_ctag(self) -> str:
        """Return the ctag for this store."""
        raise NotImplementedError(self.get_ctag)

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
        """Import a single object.

        Args:
          name: Name of the object
          content_type: Content type of the object
          data: serialized object as list of bytes
          message: Commit message
          author: Optional author
          replace_etag: Etag to replace
          requester: Optional User-Agent or client information
        Raise:
          NameExists: when the name already exists
          DuplicateUidError: when the uid already exists
        Returns: (name, etag)
        """
        raise NotImplementedError(self.import_one)

    def delete_one(
        self,
        name: str,
        message: str | None = None,
        author: str | None = None,
        etag: str | None = None,
    ) -> None:
        """Delete an item.

        Args:
          name: Filename to delete
          message: Commit message
          author: Optional author
          etag: Optional mandatory etag of object to remove
        Raises:
          NoSuchItem: when the item doesn't exist
          InvalidETag: If the specified ETag doesn't match the current
        """
        raise NotImplementedError(self.delete_one)

    def set_type(self, store_type: str) -> None:
        """Set store type.

        Args:
          store_type: New store type (one of VALID_STORE_TYPES)
        """
        raise NotImplementedError(self.set_type)

    def get_type(self) -> str:
        """Get type of this store.

        Returns: one of VALID_STORE_TYPES
        """
        ret = STORE_TYPE_OTHER
        for name, content_type, etag in self.iter_with_etag():
            if content_type == "text/calendar":
                ret = STORE_TYPE_CALENDAR
            elif content_type == "text/vcard":
                ret = STORE_TYPE_ADDRESSBOOK
        return ret

    def set_description(self, description: str) -> None:
        """Set the extended description of this store.

        Args:
          description: String with description
        """
        raise NotImplementedError(self.set_description)

    def get_description(self) -> str:
        """Get the extended description of this store."""
        raise NotImplementedError(self.get_description)

    def get_displayname(self) -> str:
        """Get the display name of this store."""
        raise NotImplementedError(self.get_displayname)

    def set_displayname(self, displayname: str) -> None:
        """Set the display name of this store."""
        raise NotImplementedError(self.set_displayname)

    def get_color(self) -> str:
        """Get the color code for this store."""
        raise NotImplementedError(self.get_color)

    def set_color(self, color: str) -> None:
        """Set the color code for this store."""
        raise NotImplementedError(self.set_color)

    def iter_changes(
        self, old_ctag: str, new_ctag: str
    ) -> Iterator[tuple[str, str, str, str]]:
        """Get changes between two versions of this store.

        Args:
          old_ctag: Old ctag (None for empty Store)
          new_ctag: New ctag
        Returns: Iterator over (name, content_type, old_etag, new_etag)
        """
        raise NotImplementedError(self.iter_changes)

    def get_comment(self) -> str:
        """Retrieve store comment.

        Returns: Comment
        """
        raise NotImplementedError(self.get_comment)

    def set_comment(self, comment: str) -> None:
        """Set comment.

        Args:
          comment: New comment to set
        """
        raise NotImplementedError(self.set_comment)

    def destroy(self) -> None:
        """Destroy this store."""
        raise NotImplementedError(self.destroy)

    def subdirectories(self) -> Iterator[str]:
        """Returns subdirectories to probe for other stores.

        Returns: List of names
        """
        raise NotImplementedError(self.subdirectories)

    def get_source_url(self) -> str:
        """Return source URL, if this is a subscription."""
        raise NotImplementedError(self.get_source_url)

    def set_source_url(self, url: str) -> None:
        """Set the source URL."""
        raise NotImplementedError(self.set_source_url)


def open_store(location: str) -> Store:
    """Open store from a location string.

    Args:
      location: Location string to open
    Returns: A `Store`
    """
    # For now, just support opening git stores
    from .git import GitStore

    return GitStore.open_from_path(location)
