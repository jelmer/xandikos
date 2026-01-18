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
import hashlib
import logging
import os
import shutil
import uuid

from . import (
    MIMETYPES,
    DuplicateUidError,
    InvalidETag,
    InvalidFileContents,
    NoSuchItem,
    Store,
    open_by_content_type,
    open_by_extension,
)
from .config import CONFIG_FILENAME
from .config import FileBasedCollectionMetadata
from .index import MemoryIndex

DEFAULT_ENCODING = "utf-8"


logger = logging.getLogger(__name__)


class VdirStore(Store):
    """A Store backed by a Vdir directory."""

    def __init__(self, path, check_for_duplicate_uids=True) -> None:
        super().__init__(MemoryIndex())
        self.path = path
        self._check_for_duplicate_uids = check_for_duplicate_uids
        # Set of blob ids that have already been scanned
        self._fname_to_uid: dict[str, str] = {}
        # Maps uids to (sha, fname)
        self._uid_to_fname: dict[str, str] = {}
        cp = configparser.ConfigParser()
        cp.read([os.path.join(self.path, CONFIG_FILENAME)])

        def save_config(cp, message):
            with open(os.path.join(self.path, CONFIG_FILENAME), "w") as f:
                cp.write(f)

        self.config = FileBasedCollectionMetadata(cp, save=save_config)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path!r})"

    def _get_etag(self, name):
        path = os.path.join(self.path, name)
        md5 = hashlib.md5()
        try:
            with open(path, "rb") as f:
                for chunk in f:
                    md5.update(chunk)
        except FileNotFoundError as exc:
            raise KeyError(name) from exc
        except IsADirectoryError as exc:
            raise KeyError(name) from exc
        return md5.hexdigest()

    def _get_raw(self, name, etag=None):
        """Get the raw contents of an object.

        Args:
          name: Name of the item
          etag: Optional etag (ignored)
        Returns: raw contents as chunks
        """
        path = os.path.join(self.path, name)
        try:
            with open(path, "rb") as f:
                return [f.read()]
        except FileNotFoundError as exc:
            raise KeyError(name) from exc
        except IsADirectoryError as exc:
            raise KeyError(name) from exc

    def _scan_uids(self):
        removed = set(self._fname_to_uid.keys())
        for name, content_type, etag in self.iter_with_etag():
            if name in removed:
                removed.remove(name)
            if name in self._fname_to_uid and self._fname_to_uid[name][0] == etag:
                continue
            fi = open_by_extension(
                self._get_raw(name, etag), name, self.extra_file_handlers
            )
            try:
                uid = fi.get_uid()
            except KeyError:
                logger.warning("No UID found in file %s", name)
                uid = None
            except InvalidFileContents as e:
                logging.warning("Unable to parse file %s: %s", name, e)
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

    def import_one(
        self,
        name,
        content_type,
        data,
        message=None,
        author=None,
        replace_etag=None,
        requester=None,
    ):
        """Import a single object.

        Args:
          name: name of the object
          content_type: Content type
          data: serialized object as list of bytes
          message: Commit message
          author: Optional author
          replace_etag: optional etag of object to replace
          requester: Optional User-Agent or client information
        Raises:
          InvalidETag: when the name already exists but with different etag
          DuplicateUidError: when the uid already exists
        Returns: etag
        """
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

        # Validate file extension matches content type
        expected_extension = MIMETYPES.guess_extension(fi.content_type)
        if expected_extension and not name.endswith(expected_extension):
            logging.warning(
                "File %s has extension mismatch: expected %s for content type %s",
                name,
                expected_extension,
                fi.content_type,
            )

        # TODO(jelmer): check that a UID is present and that all UIDs are the
        # same
        path = os.path.join(self.path, name)
        tmppath = os.path.join(self.path, name + ".tmp")
        with open(tmppath, "wb") as f:
            for chunk in fi.normalized():
                f.write(chunk)
        os.replace(tmppath, path)
        return (name, self._get_etag(name))

    def iter_with_etag(self, ctag=None):
        """Iterate over all items in the store with etag.

        Args:
          ctag: Ctag to iterate for
        Returns: iterator over (name, content_type, etag) tuples
        """
        for name in os.listdir(self.path):
            if name.endswith(".tmp"):
                continue
            if name == CONFIG_FILENAME:
                continue
            if name.endswith(".ics"):
                content_type = "text/calendar"
            elif name.endswith(".vcf"):
                content_type = "text/vcard"
            else:
                continue
            yield (name, content_type, self._get_etag(name))

    @classmethod
    def create(cls, path: str) -> "VdirStore":
        """Create a new store backed by a Vdir on disk.

        Returns: A `VdirStore`
        """
        os.mkdir(path)
        return cls(path)

    @classmethod
    def open_from_path(cls, path: str) -> "VdirStore":
        """Open a VdirStore from a path.

        Args:
          path: Path
        Returns: A `VdirStore`
        """
        return cls(path)

    def get_description(self):
        """Get extended description.

        Returns: repository description as string
        """
        return self.config.get_description()

    def set_description(self, description):
        """Set extended description.

        Args:
          description: repository description as string
        """
        self.config.set_description(description)

    def set_comment(self, comment):
        """Set comment.

        Args:
          comment: Comment
        """
        raise NotImplementedError(self.set_comment)

    def get_comment(self):
        """Get comment.

        Returns: Comment
        """
        raise NotImplementedError(self.get_comment)

    def _read_metadata(self, name):
        try:
            with open(os.path.join(self.path, name)) as f:
                return f.read().strip()
        except FileNotFoundError:
            return None
        except IsADirectoryError:
            return None

    def _write_metadata(self, name, data):
        path = os.path.join(self.path, name)
        if data is not None:
            with open(path, "w") as f:
                f.write(data)
        else:
            os.unlink(path)

    def get_color(self):
        """Get color.

        Returns: A Color code, or None
        """
        color = self._read_metadata("color")
        if color is not None:
            assert color.startswith("#")
        return color

    def set_color(self, color):
        """Set the color code for this store."""
        assert color.startswith("#")
        self._write_metadata("color", color)

    def get_source_url(self):
        """Get source URL."""
        return self._read_metadata("source")

    def set_source_url(self, url):
        """Set source URL."""
        self._write_metadata("source", url)

    def get_displayname(self):
        """Get display name.

        Returns: The display name, or None if not set
        """
        return self._read_metadata("displayname")

    def set_displayname(self, displayname):
        """Set the display name.

        Args:
          displayname: New display name
        """
        self._write_metadata("displayname", displayname)

    def iter_changes(self, old_ctag, new_ctag):
        """Get changes between two versions of this store.

        Args:
          old_ctag: Old ctag (None for empty Store)
          new_ctag: New ctag
        Returns: Iterator over (name, content_type, old_etag, new_etag)
        """
        raise NotImplementedError(self.iter_changes)

    def destroy(self):
        """Destroy this store."""
        shutil.rmtree(self.path)

    def delete_one(self, name, message=None, author=None, etag=None):
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
        except FileNotFoundError as exc:
            raise NoSuchItem(path) from exc
        except IsADirectoryError as exc:
            raise NoSuchItem(path) from exc

    def get_ctag(self):
        """Return the ctag for this store."""
        raise NotImplementedError(self.get_ctag)

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        Returns: List of names
        """
        ret = []
        for name in os.listdir(self.path):
            p = os.path.join(self.path, name)
            if os.path.isdir(p):
                ret.append(name)
        return ret
