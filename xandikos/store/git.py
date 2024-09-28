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

"""Git store."""

import configparser
import errno
import logging
import os
import shutil
import stat
import uuid
from io import BytesIO, StringIO
from typing import Optional, Iterable

import dulwich.repo
from dulwich.file import FileLocked, GitFile
from dulwich.index import Index, index_entry_from_stat, write_index_dict
from dulwich.objects import Blob, Tree
from dulwich.pack import SHA1Writer

from . import (
    DEFAULT_MIME_TYPE,
    MIMETYPES,
    VALID_STORE_TYPES,
    DuplicateUidError,
    InvalidCTag,
    InvalidETag,
    InvalidFileContents,
    LockedError,
    NoSuchItem,
    NotStoreError,
    OutOfSpaceError,
    Store,
    open_by_content_type,
    open_by_extension,
)
from .config import FILENAME as CONFIG_FILENAME
from .config import CollectionMetadata, FileBasedCollectionMetadata
from .index import MemoryIndex

DEFAULT_ENCODING = "utf-8"


logger = logging.getLogger(__name__)


class RepoCollectionMetadata(CollectionMetadata):
    def __init__(self, repo) -> None:
        self._repo = repo

    @classmethod
    def present(cls, repo):
        config = repo.get_config()
        return config.has_section((b"xandikos",))

    def get_source_url(self):
        config = self._repo.get_config()
        url = config.get(b"xandikos", b"source")
        if not url:
            raise KeyError
        return url.decode(DEFAULT_ENCODING)

    def set_source_url(self, url):
        config = self._repo.get_config()
        if url is not None:
            config.set(b"xandikos", b"source", url.encode(DEFAULT_ENCODING))
        else:
            # TODO(jelmer): Add and use config.remove()
            config.set(b"xandikos", b"source", b"")
        self._write_config(config)

    def get_color(self):
        config = self._repo.get_config()
        color = config.get(b"xandikos", b"color")
        if color == b"":
            raise KeyError
        return color.decode(DEFAULT_ENCODING)

    def set_color(self, color):
        config = self._repo.get_config()
        if color is not None:
            config.set(b"xandikos", b"color", color.encode(DEFAULT_ENCODING))
        else:
            # TODO(jelmer): Add and use config.remove()
            config.set(b"xandikos", b"color", b"")
        self._write_config(config)

    def _write_config(self, config):
        f = BytesIO()
        config.write_to_file(f)
        self._repo._put_named_file("config", f.getvalue())

    def get_displayname(self):
        config = self._repo.get_config()
        displayname = config.get(b"xandikos", b"displayname")
        if displayname == b"":
            raise KeyError
        return displayname.decode(DEFAULT_ENCODING)

    def set_displayname(self, displayname):
        config = self._repo.get_config()
        if displayname is not None:
            config.set(
                b"xandikos",
                b"displayname",
                displayname.encode(DEFAULT_ENCODING),
            )
        else:
            config.set(b"xandikos", b"displayname", b"")
        self._write_config(config)

    def get_description(self):
        desc = self._repo.get_description()
        if desc in (None, b""):
            raise KeyError
        return desc.decode(DEFAULT_ENCODING)

    def set_description(self, description):
        if description is not None:
            self._repo.set_description(description.encode(DEFAULT_ENCODING))
        else:
            self._repo.set_description(b"")

    def get_comment(self):
        config = self._repo.get_config()
        comment = config.get(b"xandikos", b"comment")
        if comment == b"":
            raise KeyError
        return comment.decode(DEFAULT_ENCODING)

    def set_comment(self, comment):
        config = self._repo.get_config()
        if comment is not None:
            config.set(b"xandikos", b"comment", comment.encode(DEFAULT_ENCODING))
        else:
            # TODO(jelmer): Add and use config.remove()
            config.set(b"xandikos", b"comment", b"")
        self._write_config(config)

    def set_type(self, store_type):
        config = self._repo.get_config()
        config.set(b"xandikos", b"type", store_type.encode(DEFAULT_ENCODING))
        self._write_config(config)

    def get_type(self):
        config = self._repo.get_config()
        store_type = config.get(b"xandikos", b"type")
        store_type = store_type.decode(DEFAULT_ENCODING)
        if store_type not in VALID_STORE_TYPES:
            logging.warning("Invalid store type %s set for %r.", store_type, self._repo)
        return store_type

    def get_order(self):
        config = self._repo.get_config()
        order = config.get(b"xandikos", b"calendar-order")
        if order == b"":
            raise KeyError
        return order.decode("utf-8")

    def set_order(self, order):
        config = self._repo.get_config()
        if order is None:
            order = ""
        config.set(b"xandikos", b"calendar-order", order.encode("utf-8"))
        self._write_config(config)


class locked_index:
    def __init__(self, path) -> None:
        self._path = path

    def __enter__(self):
        self._file = GitFile(self._path, "wb")
        self._index = Index(self._path)
        return self._index

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self._file.abort()
            return
        try:
            f = SHA1Writer(self._file)
            write_index_dict(f, self._index._byname)
        except BaseException:
            self._file.abort()
        else:
            f.close()


class GitStore(Store):
    """A Store backed by a Git Repository."""

    def __init__(
        self,
        repo,
        *,
        ref: bytes = b"HEAD",
        check_for_duplicate_uids=True,
        **kwargs,
    ) -> None:
        super().__init__(MemoryIndex(), **kwargs)
        self.ref = repo.refs.follow(ref)[0][-1]
        self.repo = repo
        # Maps uids to (sha, fname)
        self._uid_to_fname: dict[str, tuple[bytes, str]] = {}
        self._check_for_duplicate_uids = check_for_duplicate_uids
        # Set of blob ids that have already been scanned
        self._fname_to_uid: dict[str, tuple[str, str]] = {}

    def _get_etag(self, name: str) -> str:
        raise NotImplementedError(self._get_etag)

    def _import_one(
        self,
        name: str,
        data: Iterable[bytes],
        message: str,
        author: Optional[str] = None,
    ):
        raise NotImplementedError(self._import_one)

    @property
    def config(self):
        if RepoCollectionMetadata.present(self.repo):
            return RepoCollectionMetadata(self.repo)
        else:
            cp = configparser.ConfigParser()
            try:
                cf = self._get_raw(CONFIG_FILENAME)
            except KeyError:
                pass
            else:
                if cf is not None:
                    cp.read_string(b"".join(cf).decode("utf-8"))

            def save_config(cp, message):
                f = StringIO()
                cp.write(f)
                self._import_one(
                    CONFIG_FILENAME, [f.getvalue().encode("utf-8")], message
                )

            return FileBasedCollectionMetadata(cp, save=save_config)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.repo!r}, ref={self.ref!r})"

    @property
    def path(self):
        return self.repo.path

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
        name: str,
        content_type: str,
        data: Iterable[bytes],
        message: Optional[str] = None,
        author: Optional[str] = None,
        replace_etag: Optional[str] = None,
    ) -> tuple[str, str]:
        """Import a single object.

        Args:
          name: name of the object
          content_type: Content type
          data: serialized object as list of bytes
          message: Commit message
          author: Optional author
          replace_etag: optional etag of object to replace
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
        if message is None:
            try:
                old_fi = self.get_file(name, content_type, replace_etag)
            except KeyError:
                old_fi = None
            message = "\n".join(fi.describe_delta(name, old_fi))
        etag = self._import_one(name, fi.normalized(), message, author=author)
        return (name, etag.decode("ascii"))

    def _get_raw(self, name, etag=None):
        """Get the raw contents of an object.

        Args:
          name: Name of the item
          etag: Optional etag
        Returns: raw contents as chunks
        """
        if etag is None:
            etag = self._get_etag(name)
        blob = self.repo.object_store[etag.encode("ascii")]
        return blob.chunked

    def _scan_uids(self):
        removed = set(self._fname_to_uid.keys())
        for name, mode, sha in self._iterblobs():
            etag = sha.decode("ascii")
            if name in removed:
                removed.remove(name)
            if name in self._fname_to_uid and self._fname_to_uid[name][0] == etag:
                continue
            blob = self.repo.object_store[sha]
            fi = open_by_extension(blob.chunked, name, self.extra_file_handlers)
            try:
                uid = fi.get_uid()
            except KeyError:
                logger.warning("No UID found in file %s", name)
                uid = None
            except InvalidFileContents:
                logging.warning("Unable to parse file %s", name)
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

    def _iterblobs(self, ctag=None):
        raise NotImplementedError(self._iterblobs)

    def iter_with_etag(self, ctag=None):
        """Iterate over all items in the store with etag.

        Args:
          ctag: Ctag to iterate for
        Returns: iterator over (name, content_type, etag) tuples
        """
        for name, mode, sha in self._iterblobs(ctag):
            (mime_type, _) = MIMETYPES.guess_type(name)
            if mime_type is None:
                mime_type = DEFAULT_MIME_TYPE
            yield (name, mime_type, sha.decode("ascii"))

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Git repository on disk.

        Returns: A `GitStore`
        """
        raise NotImplementedError(cls.create)

    @classmethod
    def open_from_path(cls, path, **kwargs):
        """Open a GitStore from a path.

        Args:
          path: Path
        Returns: A `GitStore`
        """
        try:
            return cls.open(dulwich.repo.Repo(path), **kwargs)
        except dulwich.repo.NotGitRepository:
            raise NotStoreError(path)

    @classmethod
    def open(cls, repo, **kwargs):
        """Open a GitStore given a Repo object.

        Args:
          repo: A Dulwich `Repo`
        Returns: A `GitStore`
        """
        if repo.has_index():
            return TreeGitStore(repo, **kwargs)
        else:
            return BareGitStore(repo, **kwargs)

    def get_description(self):
        """Get extended description.

        Returns: repository description as string
        """
        try:
            return self.config.get_description()
        except KeyError:
            return None

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
        self.config.set_comment(comment)

    def get_comment(self):
        """Get comment.

        Returns: Comment
        """
        try:
            return self.config.get_comment()
        except KeyError:
            return None

    def get_color(self):
        """Get color.

        Returns: A Color code, or None
        """
        try:
            return self.config.get_color()
        except KeyError:
            return None

    def set_color(self, color):
        """Set the color code for this store."""
        self.config.set_color(color)

    def get_source_url(self):
        """Get source URL."""
        try:
            return self.config.get_source_url()
        except KeyError:
            return None

    def set_source_url(self, url):
        """Set the source URL."""
        self.config.set_source_url(url)

    def get_displayname(self):
        """Get display name.

        Returns: The display name, or None if not set
        """
        try:
            return self.config.get_displayname()
        except KeyError:
            return None

    def set_displayname(self, displayname):
        """Set the display name.

        Args:
          displayname: New display name
        """
        self.config.set_displayname(displayname)

    def set_type(self, store_type):
        """Set store type.

        Args:
          store_type: New store type (one of VALID_STORE_TYPES)
        """
        self.config.set_type(store_type)

    def get_type(self):
        """Get store type.

        This looks in git config first, then falls back to guessing.
        """
        try:
            return self.config.get_type()
        except KeyError:
            return super().get_type()

    def iter_changes(self, old_ctag, new_ctag):
        """Get changes between two versions of this store.

        Args:
          old_ctag: Old ctag (None for empty Store)
          new_ctag: New ctag
        Returns: Iterator over (name, content_type, old_etag, new_etag)
        """
        if old_ctag is None:
            t = Tree()
            self.repo.object_store.add_object(t)
            old_ctag = t.id.decode("ascii")
        previous = {
            name: (content_type, etag)
            for (name, content_type, etag) in self.iter_with_etag(old_ctag)
        }
        for name, new_content_type, new_etag in self.iter_with_etag(new_ctag):
            try:
                (old_content_type, old_etag) = previous[name]
            except KeyError:
                old_etag = None
            else:
                assert old_content_type == new_content_type
            if old_etag != new_etag:
                yield (name, new_content_type, old_etag, new_etag)
            if old_etag is not None:
                del previous[name]
        for name, (old_content_type, old_etag) in previous.items():
            yield (name, old_content_type, old_etag, None)

    def destroy(self):
        """Destroy this store."""
        shutil.rmtree(self.path)


class BareGitStore(GitStore):
    """A Store backed by a bare git repository."""

    def _get_current_tree(self):
        try:
            ref_object = self.repo[self.ref]
        except KeyError:
            return Tree()
        if isinstance(ref_object, Tree):
            return ref_object
        else:
            return self.repo.object_store[ref_object.tree]

    def _get_etag(self, name):
        tree = self._get_current_tree()
        name = name.encode(DEFAULT_ENCODING)
        return tree[name][1].decode("ascii")

    def get_ctag(self):
        """Return the ctag for this store."""
        return self._get_current_tree().id.decode("ascii")

    def _iterblobs(self, ctag=None):
        if ctag is None:
            tree = self._get_current_tree()
        else:
            try:
                tree = self.repo.object_store[ctag.encode("ascii")]
            except KeyError as exc:
                raise InvalidCTag(ctag) from exc
        for name, mode, sha in tree.iteritems():
            name = name.decode(DEFAULT_ENCODING)
            if name == CONFIG_FILENAME:
                continue
            yield (name, mode, sha)

    @classmethod
    def create_memory(cls) -> "GitStore":
        """Create a new store backed by a memory repository.

        Returns: A `GitStore`
        """
        return cls(dulwich.repo.MemoryRepo())

    def _commit_tree(self, tree_id, message, author=None):
        return self.repo.do_commit(
            message=message, tree=tree_id, ref=self.ref, author=author
        )

    def _import_one(
        self,
        name: str,
        data: Iterable[bytes],
        message: str,
        author: Optional[str] = None,
    ) -> bytes:
        """Import a single object.

        Args:
          name: Optional name of the object
          data: serialized object as bytes
          message: optional commit message
          author: optional author
        Returns: etag
        """
        b = Blob()
        b.chunked = data
        tree = self._get_current_tree()
        old_tree_id = tree.id
        name_enc = name.encode(DEFAULT_ENCODING)
        tree[name_enc] = (0o644 | stat.S_IFREG, b.id)
        self.repo.object_store.add_objects([(tree, ""), (b, name_enc)])
        if tree.id != old_tree_id:
            self._commit_tree(tree.id, message.encode(DEFAULT_ENCODING), author=author)
        return b.id

    def delete_one(self, name, message=None, author=None, etag=None):
        """Delete an item.

        Args:
          name: Filename to delete
          message; Commit message
          author: Optional author to store
          etag: Optional mandatory etag of object to remove
        Raises:
          NoSuchItem: when the item doesn't exist
          InvalidETag: If the specified ETag doesn't match the curren
        """
        tree = self._get_current_tree()
        name_enc = name.encode(DEFAULT_ENCODING)
        try:
            current_sha = tree[name_enc][1]
        except KeyError as exc:
            raise NoSuchItem(name) from exc
        if etag is not None and current_sha != etag.encode("ascii"):
            raise InvalidETag(name, etag, current_sha.decode("ascii"))
        del tree[name_enc]
        self.repo.object_store.add_objects([(tree, "")])
        if message is None:
            fi = open_by_extension(
                self.repo.object_store[current_sha].chunked,
                name,
                self.extra_file_handlers,
            )
            message = "Delete " + fi.describe(name)
        self._commit_tree(tree.id, message.encode(DEFAULT_ENCODING), author=author)

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Git repository on disk.

        Returns: A `GitStore`
        """
        os.mkdir(path)
        return cls(dulwich.repo.Repo.init_bare(path))

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        Returns: List of names
        """
        # Or perhaps just return all subdirectories but filter out
        # Git-owned ones?
        return []


class TreeGitStore(GitStore):
    """A Store that backs onto a treefull Git repository."""

    @classmethod
    def create(cls, path, bare=True):
        """Create a new store backed by a Git repository on disk.

        Returns: A `GitStore`
        """
        os.mkdir(path)
        return cls(dulwich.repo.Repo.init(path))

    def _get_etag(self, name):
        index = self.repo.open_index()
        name = name.encode(DEFAULT_ENCODING)
        return index[name].sha.decode("ascii")

    def _commit_tree(self, index, message, author=None):
        tree = index.commit(self.repo.object_store)
        return self.repo.do_commit(message=message, author=author, tree=tree)

    def _import_one(
        self,
        name: str,
        data: Iterable[bytes],
        message: str,
        author: Optional[str] = None,
    ) -> bytes:
        """Import a single object.

        Args:
          name: name of the object
          data: serialized object as list of bytes
          message: Commit message
          author: Optional author
        Returns: etag
        """
        try:
            with locked_index(self.repo.index_path()) as index:
                p = os.path.join(self.repo.path, name)
                with open(p, "wb") as f:
                    f.writelines(data)
                st = os.lstat(p)
                blob = Blob.from_string(b"".join(data))
                encoded_name = name.encode(DEFAULT_ENCODING)
                if encoded_name not in index or blob.id != index[encoded_name].sha:
                    self.repo.object_store.add_object(blob)
                    index[encoded_name] = index_entry_from_stat(st, blob.id)
                    self._commit_tree(
                        index, message.encode(DEFAULT_ENCODING), author=author
                    )
                return blob.id
        except FileLocked as exc:
            raise LockedError(name) from exc
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise OutOfSpaceError() from exc
            raise

    def delete_one(self, name, message=None, author=None, etag=None):
        """Delete an item.

        Args:
          name: Filename to delete
          message: Commit message
          author: Optional author
          etag: Optional mandatory etag of object to remove
        Raise:
          NoSuchItem: when the item doesn't exist
          InvalidETag: If the specified ETag doesn't match the curren
        """
        p = os.path.join(self.repo.path, name)
        try:
            with open(p, "rb") as f:
                current_blob = Blob.from_string(f.read())
        except FileNotFoundError as exc:
            raise NoSuchItem(name) from exc
        except IsADirectoryError as exc:
            raise NoSuchItem(name) from exc
        if message is None:
            fi = open_by_extension(current_blob.chunked, name, self.extra_file_handlers)
            message = "Delete " + fi.describe(name)
        if etag is not None:
            with open(p, "rb") as f:
                current_etag = current_blob.id
            if etag.encode("ascii") != current_etag:
                raise InvalidETag(name, etag, current_etag.decode("ascii"))
        try:
            with locked_index(self.repo.index_path()) as index:
                os.unlink(p)
                del index[name.encode(DEFAULT_ENCODING)]
                self._commit_tree(
                    index, message.encode(DEFAULT_ENCODING), author=author
                )
        except FileLocked:
            raise LockedError(name)

    def get_ctag(self):
        """Return the ctag for this store."""
        index = self.repo.open_index()
        return index.commit(self.repo.object_store).decode("ascii")

    def _iterblobs(self, ctag=None):
        """Iterate over all items in the store with etag.

        :yield: (name, etag) tuples
        """
        if ctag is not None:
            try:
                tree = self.repo.object_store[ctag.encode("ascii")]
            except KeyError as exc:
                raise InvalidCTag(ctag) from exc
            for name, mode, sha in tree.iteritems():
                name = name.decode(DEFAULT_ENCODING)
                if name == CONFIG_FILENAME:
                    continue
                yield (name, mode, sha)
        else:
            index = self.repo.open_index()
            for name, sha, mode in index.iterobjects():
                name = name.decode(DEFAULT_ENCODING)
                if name == CONFIG_FILENAME:
                    continue
                yield (name, mode, sha)

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        Returns: List of names
        """
        ret = []
        for name in os.listdir(self.path):
            if name == dulwich.repo.CONTROLDIR:
                continue
            p = os.path.join(self.path, name)
            if os.path.isdir(p):
                ret.append(name)
        return ret
