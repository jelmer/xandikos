# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooij <jelmer@jelmer.uk>
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
import os
import shutil
import stat
import uuid

from dulwich.objects import Blob, Tree
import dulwich.repo

_DEFAULT_COMMITTER_IDENTITY = b'Xandikos <xandikos>'

STORE_TYPE_ADDRESSBOOK = 'addressbook'
STORE_TYPE_CALENDAR = 'calendar'
STORE_TYPE_OTHER = 'other'
VALID_STORE_TYPES = (
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_OTHER)

MIMETYPES = mimetypes.MimeTypes()
MIMETYPES.add_type('text/calendar', '.ics')
MIMETYPES.add_type('text/vcard', '.vcf')

DEFAULT_MIME_TYPE = 'application/octet-stream'
DEFAULT_ENCODING = 'utf-8'


logger = logging.getLogger(__name__)


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

    def describe(self, name):
        """Describe the contents of this file.

        Used in e.g. commit messages.
        """
        return name

    def get_uid(self):
        """Return UID.

        :raise NotImplementedError: If UIDs aren't supported for this format
        :raise KeyError: If there is no UID set on this file
        :return: UID
        """
        raise NotImplementedError(self.get_uid)

    def describe_delta(self, name, previous):
        """Describe the important difference between this and previous one.

        :param name: File name
        :param previous: Previous file to compare to.
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

        :param store_type: New store type (one of STORE_TYPE_ADDRESSBOOK,
            STORE_TYPE_CALENDAR, STORE_TYPE_OTHER)
        """
        raise NotImplementedError(self.set_type)

    def get_type(self):
        """Get type of this store.

        :return: one of [STORE_TYPE_ADDRESSBOOK, STORE_TYPE_CALENDAR,
                         STORE_TYPE_OTHER]
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


class GitStore(Store):
    """A Store backed by a Git Repository.
    """

    def __init__(self, repo, ref=b'refs/heads/master',
                 check_for_duplicate_uids=True):
        super(GitStore, self).__init__()
        self.ref = ref
        self.repo = repo
        # Maps uids to (sha, fname)
        self._uid_to_fname = {}
        self._check_for_duplicate_uids = check_for_duplicate_uids
        # Set of blob ids that have already been scanned
        self._fname_to_uid = {}

    def __repr__(self):
        return "%s(%r, ref=%r)" % (type(self).__name__, self.repo, self.ref)

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
        fi = open_by_content_type(data, content_type, self.extra_file_handlers)
        if name is None:
            name = str(uuid.uuid4()) + MIMETYPES.guess_extension(content_type)
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
            message = '\n'.join(fi.describe_delta(name, old_fi))
        etag = self._import_one(name, data, message, author=author)
        return (name, etag.decode('ascii'))

    def _get_raw(self, name, etag=None):
        """Get the raw contents of an object.

        :param name: Name of the item
        :param etag: Optional etag
        :return: raw contents as chunks
        """
        if etag is None:
            etag = self._get_etag(name)
        blob = self.repo.object_store[etag.encode('ascii')]
        return blob.chunked

    def _scan_uids(self):
        removed = set(self._fname_to_uid.keys())
        for (name, mode, sha) in self._iterblobs():
            etag = sha.decode('ascii')
            if name in removed:
                removed.remove(name)
            if (name in self._fname_to_uid and
                    self._fname_to_uid[name][0] == etag):
                continue
            blob = self.repo.object_store[sha]
            fi = open_by_extension(blob.chunked, name,
                                   self.extra_file_handlers)
            try:
                uid = fi.get_uid()
            except KeyError:
                logger.warning('No UID found in file %s', name)
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

        :param ctag: Ctag to iterate for
        :yield: (name, content_type, etag) tuples
        """
        for (name, mode, sha) in self._iterblobs(ctag):
            (mime_type, _) = MIMETYPES.guess_type(name)
            if mime_type is None:
                mime_type = DEFAULT_MIME_TYPE
            yield (name, mime_type, sha.decode('ascii'))

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Git repository on disk.

        :return: A `GitStore`
        """
        raise NotImplementedError(cls.create)

    @classmethod
    def open_from_path(cls, path):
        """Open a GitStore from a path.

        :param path: Path
        :return: A `GitStore`
        """
        try:
            return cls.open(dulwich.repo.Repo(path))
        except dulwich.repo.NotGitRepository:
            raise NotStoreError(path)

    @classmethod
    def open(cls, repo):
        """Open a GitStore given a Repo object.

        :param repo: A Dulwich `Repo`
        :return: A `GitStore`
        """
        if repo.has_index():
            return TreeGitStore(repo)
        else:
            return BareGitStore(repo)

    def get_description(self):
        """Get extended description.

        :return: repository description as string
        """
        desc = self.repo.get_description()
        if desc is not None:
            desc = desc.decode(DEFAULT_ENCODING)
        return desc

    def set_description(self, description):
        """Set extended description.

        :param description: repository description as string
        """
        return self.repo.set_description(description.encode(DEFAULT_ENCODING))

    def set_comment(self, comment):
        """Set comment.

        :param comment: Comment
        """
        config = self.repo.get_config()
        config.set(b'xandikos', b'comment', comment.encode(DEFAULT_ENCODING))
        config.write_to_path()

    def get_comment(self):
        """Get comment.

        :return: Comment
        """
        config = self.repo.get_config()
        try:
            comment = config.get(b'xandikos', b'comment')
        except KeyError:
            return None
        else:
            return comment.decode(DEFAULT_ENCODING)

    def get_color(self):
        """Get color.

        :return: A Color code, or None
        """
        config = self.repo.get_config()
        try:
            color = config.get(b'xandikos', b'color')
        except KeyError:
            return None
        else:
            return color.decode(DEFAULT_ENCODING)

    def set_color(self, color):
        """Set the color code for this store."""
        config = self.repo.get_config()
        # Strip leading # to work around
        # https://github.com/jelmer/dulwich/issues/511
        # TODO(jelmer): Drop when that bug gets fixed.
        config.set(
            b'xandikos', b'color',
            color.lstrip('#').encode(DEFAULT_ENCODING) if color else b'')
        config.write_to_path()

    def get_displayname(self):
        """Get display name.

        :return: The display name, or None if not set
        """
        config = self.repo.get_config()
        try:
            displayname = config.get(b'xandikos', b'displayname')
        except KeyError:
            return None
        else:
            return displayname.decode(DEFAULT_ENCODING)

    def set_displayname(self, displayname):
        """Set the display name.

        :param displayname: New display name
        """
        config = self.repo.get_config()
        config.set(b'xandikos', b'displayname',
                   displayname.encode(DEFAULT_ENCODING))
        config.write_to_path()

    def set_type(self, store_type):
        """Set store type.

        :param store_type: New store type (one of STORE_TYPE_ADDRESSBOOK,
            STORE_TYPE_CALENDAR, STORE_TYPE_OTHER)
        """
        config = self.repo.get_config()
        config.set(b'xandikos', b'type', store_type.encode(DEFAULT_ENCODING))
        config.write_to_path()

    def get_type(self):
        """Get store type.

        This looks in git config first, then falls back to guessing.
        """
        config = self.repo.get_config()
        try:
            store_type = config.get(b'xandikos', b'type')
        except KeyError:
            return super(GitStore, self).get_type()
        else:
            store_type = store_type.decode(DEFAULT_ENCODING)
            if store_type not in VALID_STORE_TYPES:
                logging.warning(
                    'Invalid store type %s set for %r.',
                    store_type, self.repo)
            return store_type

    def iter_changes(self, old_ctag, new_ctag):
        """Get changes between two versions of this store.

        :param old_ctag: Old ctag (None for empty Store)
        :param new_ctag: New ctag
        :return: Iterator over (name, content_type, old_etag, new_etag)
        """
        if old_ctag is None:
            t = Tree()
            self.repo.object_store.add_object(t)
            old_ctag = t.id.decode('ascii')
        previous = {
            name: (content_type, etag)
            for (name, content_type, etag) in self.iter_with_etag(old_ctag)
        }
        for (name, new_content_type, new_etag) in (
                self.iter_with_etag(new_ctag)):
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
        for (name, (old_content_type, old_etag)) in previous.items():
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
        return tree[name][1].decode('ascii')

    def get_ctag(self):
        """Return the ctag for this store."""
        return self._get_current_tree().id.decode('ascii')

    def _iterblobs(self, ctag=None):
        if ctag is None:
            tree = self._get_current_tree()
        else:
            tree = self.repo.object_store[ctag.encode('ascii')]
        for (name, mode, sha) in tree.iteritems():
            name = name.decode(DEFAULT_ENCODING)
            yield (name, mode, sha)

    @classmethod
    def create_memory(cls):
        """Create a new store backed by a memory repository.

        :return: A `GitStore`
        """
        return cls(dulwich.repo.MemoryRepo())

    def _commit_tree(self, tree_id, message, author=None):
        try:
            committer = self.repo._get_user_identity()
        except KeyError:
            committer = _DEFAULT_COMMITTER_IDENTITY
        return self.repo.do_commit(message=message, tree=tree_id, ref=self.ref,
                                   committer=committer, author=author)

    def _import_one(self, name, data, message, author=None):
        """Import a single object.

        :param name: Optional name of the object
        :param data: serialized object as bytes
        :param message: optional commit message
        :param author: optional author
        :return: etag
        """
        b = Blob()
        b.chunked = data
        tree = self._get_current_tree()
        name_enc = name.encode(DEFAULT_ENCODING)
        tree[name_enc] = (0o644 | stat.S_IFREG, b.id)
        self.repo.object_store.add_objects([(tree, ''), (b, name_enc)])
        self._commit_tree(tree.id, message.encode(DEFAULT_ENCODING),
                          author=author)
        return b.id

    def delete_one(self, name, message=None, author=None, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param message; Commit message
        :param author: Optional author to store
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the curren
        """
        tree = self._get_current_tree()
        name_enc = name.encode(DEFAULT_ENCODING)
        try:
            current_sha = tree[name_enc][1]
        except KeyError:
            raise NoSuchItem(name)
        if etag is not None and current_sha != etag.encode('ascii'):
            raise InvalidETag(name, etag, current_sha.decode('ascii'))
        del tree[name_enc]
        self.repo.object_store.add_objects([(tree, '')])
        if message is None:
            fi = open_by_extension(
                self.repo.object_store[current_sha].chunked, name,
                self.extra_file_handlers)
            message = "Delete " + fi.describe(name)
        self._commit_tree(tree.id, message.encode(DEFAULT_ENCODING),
                          author=author)

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Git repository on disk.

        :return: A `GitStore`
        """
        os.mkdir(path)
        return cls(dulwich.repo.Repo.init_bare(path))

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        :return: List of names
        """
        # Or perhaps just return all subdirectories but filter out
        # Git-owned ones?
        return []


class TreeGitStore(GitStore):
    """A Store that backs onto a treefull Git repository."""

    @classmethod
    def create(cls, path, bare=True):
        """Create a new store backed by a Git repository on disk.

        :return: A `GitStore`
        """
        os.mkdir(path)
        return cls(dulwich.repo.Repo.init(path))

    def _get_etag(self, name):
        index = self.repo.open_index()
        name = name.encode(DEFAULT_ENCODING)
        return index[name].sha.decode('ascii')

    def _commit_tree(self, message, author=None):
        try:
            committer = self.repo._get_user_identity()
        except KeyError:
            committer = _DEFAULT_COMMITTER_IDENTITY
        return self.repo.do_commit(message=message, committer=committer,
                                   author=author)

    def _import_one(self, name, data, message, author=None):
        """Import a single object.

        :param name: name of the object
        :param data: serialized object as list of bytes
        :param message: Commit message
        :param author: Optional author
        :return: etag
        """
        p = os.path.join(self.repo.path, name)
        with open(p, 'wb') as f:
            f.writelines(data)
        self.repo.stage(name)
        etag = self.repo.open_index()[name.encode(DEFAULT_ENCODING)].sha
        self._commit_tree(message.encode(DEFAULT_ENCODING), author=author)
        return etag

    def delete_one(self, name, message=None, author=None, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param message: Commit message
        :param author: Optional author
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the curren
        """
        p = os.path.join(self.repo.path, name)
        try:
            with open(p, 'rb') as f:
                current_blob = Blob.from_string(f.read())
        except IOError:
            raise NoSuchItem(name)
        if message is None:
            fi = open_by_extension(current_blob.chunked, name,
                                   self.extra_file_handlers)
            message = 'Delete ' + fi.describe(name)
        if etag is not None:
            with open(p, 'rb') as f:
                current_etag = current_blob.id
            if etag.encode('ascii') != current_etag:
                raise InvalidETag(name, etag, current_etag.decode('ascii'))
        os.unlink(p)
        self.repo.stage(name)
        self._commit_tree(message.encode(DEFAULT_ENCODING), author=author)

    def get_ctag(self):
        """Return the ctag for this store."""
        index = self.repo.open_index()
        return index.commit(self.repo.object_store).decode('ascii')

    def _iterblobs(self, ctag=None):
        """Iterate over all items in the store with etag.

        :yield: (name, etag) tuples
        """
        if ctag is not None:
            tree = self.repo.object_store[ctag.encode('ascii')]
            for (name, mode, sha) in tree.iteritems():
                name = name.decode(DEFAULT_ENCODING)
                yield (name, mode, sha)
        else:
            index = self.repo.open_index()
            for (name, sha, mode) in index.iterblobs():
                name = name.decode(DEFAULT_ENCODING)
                yield (name, mode, sha)

    def subdirectories(self):
        """Returns subdirectories to probe for other stores.

        :return: List of names
        """
        ret = []
        for name in os.listdir(self.path):
            if name == dulwich.repo.CONTROLDIR:
                continue
            p = os.path.join(self.path, name)
            if os.path.isdir(p):
                ret.append(name)
        return ret


def open_store(location):
    """Open store from a location string.

    :param location: Location string to open
    :return: A `Store`
    """
    # For now, just support opening git stores
    return GitStore.open_from_path(location)
