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

"""vdir store.

See https://github.com/pimutils/vdirsyncer/blob/master/docs/vdir.rst
"""

import configparser
import errno
import hashlib
import logging
import os
import shutil
import uuid

from . import (
    MIMETYPES,
    Store,
    DuplicateUidError,
    InvalidETag,
    InvalidFileContents,
    NoSuchItem,
    open_by_content_type,
    open_by_extension,
)
from .config import (
    FileBasedCollectionMetadata,
    FILENAME as CONFIG_FILENAME,
)
from .index import MemoryIndex


DEFAULT_ENCODING = 'utf-8'


logger = logging.getLogger(__name__)


class VdirStore(Store):
    """A Store backed by a Vdir directory.
    """

    def __init__(self, path, check_for_duplicate_uids=True):
        super(VdirStore, self).__init__(MemoryIndex())
        self.path = path
        self._check_for_duplicate_uids = check_for_duplicate_uids
        # Set of blob ids that have already been scanned
        self._fname_to_uid = {}
        # Maps uids to (sha, fname)
        self._uid_to_fname = {}
        cp = configparser.ConfigParser()
        cp.read([os.path.join(self.path, CONFIG_FILENAME)])

        def save_config(cp, message):
            with open(os.path.join(self.path, CONFIG_FILENAME), 'w') as f:
                cp.write(f)
        self.config = FileBasedCollectionMetadata(cp, save=save_config)

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.path)

    def _get_etag(self, name):
        path = os.path.join(self.path, name)
        md5 = hashlib.md5()
        try:
            with open(path, 'rb') as f:
                for chunk in f:
                    md5.update(chunk)
        except IOError as e:
            if e.errno == errno.ENOENT:
                raise KeyError
            raise
        return md5.hexdigest()

    def _get_raw(self, name, etag=None):
        """Get the raw contents of an object.

        :param name: Name of the item
        :param etag: Optional etag (ignored)
        :return: raw contents as chunks
        """
        path = os.path.join(self.path, name)
        try:
            with open(path, 'rb') as f:
                return [f.read()]
        except IOError as e:
            if e.errno == errno.ENOENT:
                raise KeyError
            raise

    def _scan_uids(self):
        removed = set(self._fname_to_uid.keys())
        for (name, content_type, etag) in self.iter_with_etag():
            if name in removed:
                removed.remove(name)
            if (name in self._fname_to_uid and
                    self._fname_to_uid[name][0] == etag):
                continue
            fi = open_by_extension(self._get_raw(name, etag), name,
                                   self.extra_file_handlers)
            try:
                uid = fi.get_uid()
            except KeyError:
                logger.warning('No UID found in file %s', name)
                uid = None
            except InvalidFileContents:
                logging.warning('Unable to parse file %s', name)
                uid = None
            except NotImplementedError:
                # This file type doesn't support UIDs
                uid = None
            self._fname_to_uid[name] = (etag, uid)
            if uid is not None:
                self._uid_to_fname[uid] = (name, etag)
        for name in removed:
            (unused_etag, uid) = self._fname_to_uid[name]
            if uid is not None:
                del self._uid_to_fname[uid]
            del self._fname_to_uid[name]

    def _check_duplicate(self, uid, name, replace_etag):
        if uid is not None and self._check_for_duplicate_uids:
            self._scan_uids()
            try:
                (existing_name, _) = self._uid_to_fname[uid]
            except KeyError:
                pass
            else:
                if existing_name != name:
                    raise DuplicateUidError(uid, existing_name, name)

        try:
            etag = self._get_etag(name)
        except KeyError:
            etag = None
        if replace_etag is not None and etag != replace_etag:
            raise InvalidETag(name, etag, replace_etag)
        return etag

    def import_one(self, name, content_type, data, message=None, author=None,
                   replace_etag=None):
        """Import a single object.

        :param name: name of the object
        :param content_type: Content type
        :param data: serialized object as list of bytes
        :param message: Commit message
        :param author: Optional author
        :param replace_etag: optional etag of object to replace
        :raise InvalidETag: when the name already exists but with different
                            etag
        :raise DuplicateUidError: when the uid already exists
        :return: etag
        """
        if content_type is None:
            fi = open_by_extension(data, name, self.extra_file_handlers)
        else:
            fi = open_by_content_type(
                data, content_type, self.extra_file_handlers)
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

        # TODO(jelmer): Check that extensions match content type:
        #  if this is a vCard, the extension should be .vcf
        #  if this is a iCalendar, the extension should be .ics
        # TODO(jelmer): check that a UID is present and that all UIDs are the
        # same
        path = os.path.join(self.path, name)
        tmppath = os.path.join(self.path, name + '.tmp')
        with open(tmppath, 'wb') as f:
            for chunk in fi.normalized():
                f.write(chunk)
        os.replace(tmppath, path)
        return (name, self._get_etag(name))

    def iter_with_etag(self, ctag=None):
        """Iterate over all items in the store with etag.

        :param ctag: Ctag to iterate for
        :yield: (name, content_type, etag) tuples
        """
        for name in os.listdir(self.path):
            if name.endswith('.tmp'):
                continue
            if name == CONFIG_FILENAME:
                continue
            if name.endswith('.ics'):
                content_type = 'text/calendar'
            elif name.endswith('.vcf'):
                content_type = 'text/vcard'
            else:
                continue
            yield (name, content_type, self._get_etag(name))

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Vdir on disk.

        :return: A `VdirStore`
        """
        os.mkdir(path)
        return cls(path)

    @classmethod
    def open_from_path(cls, path):
        """Open a VdirStore from a path.

        :param path: Path
        :return: A `VdirStore`
        """
        return cls(path)

    def get_description(self):
        """Get extended description.

        :return: repository description as string
        """
        return self.config.get_description()

    def set_description(self, description):
        """Set extended description.

        :param description: repository description as string
        """
        self.config.set_description(description)

    def set_comment(self, comment):
        """Set comment.

        :param comment: Comment
        """
        raise NotImplementedError(self.set_comment)

    def get_comment(self):
        """Get comment.

        :return: Comment
        """
        raise NotImplementedError(self.get_comment)

    def _read_metadata(self, name):
        try:
            with open(os.path.join(self.path, name), 'r') as f:
                return f.read().strip()
        except EnvironmentError:
            return None

    def _write_metadata(self, name, data):
        path = os.path.join(self.path, name)
        if data is not None:
            with open(path, 'w') as f:
                f.write(data)
        else:
            os.unlink(path)

    def get_color(self):
        """Get color.

        :return: A Color code, or None
        """
        color = self._read_metadata('color')
        if color is not None:
            assert color.startswith('#')
        return color

    def set_color(self, color):
        """Set the color code for this store."""
        assert color.startswith('#')
        self._write_metadata('color', color)

    def get_displayname(self):
        """Get display name.

        :return: The display name, or None if not set
        """
        return self._read_metadata('displayname')

    def set_displayname(self, displayname):
        """Set the display name.

        :param displayname: New display name
        """
        self._write_metadata('displayname', displayname)

    def iter_changes(self, old_ctag, new_ctag):
        """Get changes between two versions of this store.

        :param old_ctag: Old ctag (None for empty Store)
        :param new_ctag: New ctag
        :return: Iterator over (name, content_type, old_etag, new_etag)
        """
        raise NotImplementedError(self.iter_changes)

    def destroy(self):
        """Destroy this store."""
        shutil.rmtree(self.path)

    def delete_one(self, name, message=None, author=None, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param message: Commit message
        :param author: Optional author
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the curren
        """
        path = os.path.join(self.path, name)
        if etag is not None:
            try:
                current_etag = self._get_etag(name)
            except KeyError:
                raise NoSuchItem(name)
            if etag != current_etag:
                raise InvalidETag(name, etag, current_etag)
        try:
            os.unlink(path)
        except EnvironmentError as e:
            if e.errno == errno.ENOENT:
                raise NoSuchItem(path)
            raise

    def get_ctag(self):
        """Return the ctag for this store."""
        raise NotImplementedError(self.get_ctag)

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        :return: List of names
        """
        ret = []
        for name in os.listdir(self.path):
            p = os.path.join(self.path, name)
            if os.path.isdir(p):
                ret.append(name)
        return ret
