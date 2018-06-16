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

import mimetypes

STORE_TYPE_ADDRESSBOOK = 'addressbook'
STORE_TYPE_CALENDAR = 'calendar'
STORE_TYPE_PRINCIPAL = 'principal'
STORE_TYPE_SCHEDULE_INBOX = 'schedule-inbox'
STORE_TYPE_SCHEDULE_OUTBOX = 'schedule-outbox'
STORE_TYPE_OTHER = 'other'
VALID_STORE_TYPES = (
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_PRINCIPAL,
    STORE_TYPE_SCHEDULE_INBOX,
    STORE_TYPE_SCHEDULE_OUTBOX,
    STORE_TYPE_OTHER)

MIMETYPES = mimetypes.MimeTypes()
MIMETYPES.add_type('text/calendar', '.ics')
MIMETYPES.add_type('text/vcard', '.vcf')

DEFAULT_MIME_TYPE = 'application/octet-stream'


class File(object):
    """A file type handler."""

    def __init__(self, content, content_type):
        self.content = content
        self.content_type = content_type

    def validate(self):
        """Verify that file contents are valid.

        :raise InvalidFileContents: Raised if a file is not valid
        """
        pass

    def normalized(self):
        """Return a normalized version of the file.
        """
        return self.content

    def describe(self, name):
        """Describe the contents of this file.

        Used in e.g. commit messages.
        """
        return name

    def get_uid(self):
        """Return UID.

        :raise NotImplementedError: If UIDs aren't supported for this format
        :raise KeyError: If there is no UID set on this file
        :raise InvalidFileContents: If the file is misformatted
        :return: UID
        """
        raise NotImplementedError(self.get_uid)

    def describe_delta(self, name, previous):
        """Describe the important difference between this and previous one.

        :param name: File name
        :param previous: Previous file to compare to.
        :raise InvalidFileContents: If the file is misformatted
        :return: List of strings describing change
        """
        assert name is not None
        item_description = self.describe(name)
        assert item_description is not None
        if previous is None:
            yield "Added " + item_description
        else:
            yield "Modified " + item_description


def open_by_content_type(content, content_type, extra_file_handlers):
    """Open a file based on content type.

    :param content: list of bytestrings with content
    :param content_type: MIME type
    :return: File instance
    """
    return extra_file_handlers.get(content_type.split(';')[0], File)(
        content, content_type)


def open_by_extension(content, name, extra_file_handlers):
    """Open a file based on the filename extension.

    :param content: list of bytestrings with content
    :param name: Name of file to open
    :return: File instance
    """
    (mime_type, _) = MIMETYPES.guess_type(name)
    if mime_type is None:
        mime_type = DEFAULT_MIME_TYPE
    return open_by_content_type(content, mime_type,
                                extra_file_handlers=extra_file_handlers)


class DuplicateUidError(Exception):
    """UID already exists in store."""

    def __init__(self, uid, existing_name, new_name):
        self.uid = uid
        self.existing_name = existing_name
        self.new_name = new_name


class NoSuchItem(Exception):
    """No such item."""

    def __init__(self, name):
        self.name = name


class InvalidETag(Exception):
    """Unexpected value for etag."""

    def __init__(self, name, expected_etag, got_etag):
        self.name = name
        self.expected_etag = expected_etag
        self.got_etag = got_etag


class NotStoreError(Exception):
    """Not a store."""

    def __init__(self, path):
        self.path = path


class InvalidFileContents(Exception):
    """Invalid file contents."""

    def __init__(self, content_type, data):
        self.content_type = content_type
        self.data = data


class Store(object):
    """A object store."""

    def __init__(self):
        self.extra_file_handlers = {}

    def load_extra_file_handler(self, file_handler):
        self.extra_file_handlers[file_handler.content_type] = file_handler

    def iter_with_etag(self):
        """Iterate over all items in the store with etag.

        :yield: (name, content_type, etag) tuples
        """
        raise NotImplementedError(self.iter_with_etag)

    def get_file(self, name, content_type=None, etag=None):
        """Get the contents of an object.

        :return: A File object
        """
        if content_type is None:
            return open_by_extension(
                self._get_raw(name, etag), name,
                extra_file_handlers=self.extra_file_handlers)
        else:
            return open_by_content_type(
                self._get_raw(name, etag), content_type,
                extra_file_handlers=self.extra_file_handlers)

    def _get_raw(self, name, etag):
        """Get the raw contents of an object.

        :return: raw contents
        """
        raise NotImplementedError(self._get_raw)

    def get_ctag(self):
        """Return the ctag for this store."""
        raise NotImplementedError(self.get_ctag)

    def import_one(self, name, data, message=None, author=None,
                   replace_etag=None):
        """Import a single object.

        :param name: Name of the object
        :param data: serialized object as list of bytes
        :param message: Commit message
        :param author: Optional author
        :param replace_etag: Etag to replace
        :raise NameExists: when the name already exists
        :raise DuplicateUidError: when the uid already exists
        :return: (name, etag)
        """
        raise NotImplementedError(self.import_one)

    def delete_one(self, name, message=None, author=None, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param author: Optional author
        :param message: Commit message
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the current
        """
        raise NotImplementedError(self.delete_one)

    def set_type(self, store_type):
        """Set store type.

        :param store_type: New store type (one of VALID_STORE_TYPES)
        """
        raise NotImplementedError(self.set_type)

    def get_type(self):
        """Get type of this store.

        :return: one of VALID_STORE_TYPES
        """
        ret = STORE_TYPE_OTHER
        for (name, content_type, etag) in self.iter_with_etag():
            if content_type == 'text/calendar':
                ret = STORE_TYPE_CALENDAR
            elif content_type == 'text/vcard':
                ret = STORE_TYPE_ADDRESSBOOK
        return ret

    def set_description(self, description):
        """Set the extended description of this store.

        :param description: String with description
        """
        raise NotImplementedError(self.set_description)

    def get_description(self):
        """Get the extended description of this store.
        """
        raise NotImplementedError(self.get_description)

    def get_displayname(self):
        """Get the display name of this store.
        """
        raise NotImplementedError(self.get_displayname)

    def set_displayname(self):
        """Set the display name of this store.
        """
        raise NotImplementedError(self.set_displayname)

    def get_color(self):
        """Get the color code for this store."""
        raise NotImplementedError(self.get_color)

    def set_color(self, color):
        """Set the color code for this store."""
        raise NotImplementedError(self.set_color)

    def iter_changes(self, old_ctag, new_ctag):
        """Get changes between two versions of this store.

        :param old_ctag: Old ctag (None for empty Store)
        :param new_ctag: New ctag
        :return: Iterator over (name, content_type, old_etag, new_etag)
        """
        raise NotImplementedError(self.iter_changes)

    def get_comment(self):
        """Retrieve store comment.

        :return: Comment
        """
        raise NotImplementedError(self.get_comment)

    def set_comment(self, comment):
        """Set comment.

        :param comment: New comment to set
        """
        raise NotImplementedError(self.set_comment)

    def destroy(self):
        """Destroy this store."""
        raise NotImplementedError(self.destroy)

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        :return: List of names
        """
        raise NotImplementedError(self.subdirectories)


def open_store(location):
    """Open store from a location string.

    :param location: Location string to open
    :return: A `Store`
    """
    # For now, just support opening git stores
    from .git import GitStore
    return GitStore.open_from_path(location)
