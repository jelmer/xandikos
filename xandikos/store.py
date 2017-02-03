# Xandikos
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
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
import os
import stat

from icalendar.cal import Calendar

from dulwich.objects import Blob, Tree
import dulwich.repo

_DEFAULT_COMMITTER_IDENTITY = b'Xandikos <xandikos>'
ICALENDAR_EXTENSION = '.ics'
VCARD_EXTENSION = '.vcf'

STORE_TYPE_ADDRESSBOOK = 'addressbook'
STORE_TYPE_CALENDAR = 'calendar'
STORE_TYPE_OTHER = 'other'
VALID_STORE_TYPES = (
    STORE_TYPE_ADDRESSBOOK,
    STORE_TYPE_CALENDAR,
    STORE_TYPE_OTHER)


DEFAULT_ENCODING = 'utf-8'


logger = logging.getLogger(__name__)


def ExtractCalendarUID(cal):
    """Extract the UID from a VCalendar file.

    :param cal: Calendar, possibly serialized.
    :return: UID
    """
    if type(cal) in (bytes, str):
        cal = Calendar.from_ical(cal)
    for component in cal.subcomponents:
        try:
            return component["UID"]
        except KeyError:
            pass
    raise KeyError


def ExtractUID(name, data):
    """Extract UID from a file.

    :param name: Name of the file
    :param data: Data (possibly serialized)
    :return: UID
    """
    if name.endswith(ICALENDAR_EXTENSION):
        return ExtractCalendarUID(data)
    else:
        return None


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


class Store(object):
    """A object store."""

    def iter_with_etag(self):
        """Iterate over all items in the store with etag.

        :yield: (name, etag) tuples
        """
        raise NotImplementedError(self.iter_with_etag)

    def get_raw(self, name, etag):
        """Get the raw contents of an object.

        :return: raw contents
        """
        raise NotImplementedError(self.get_raw)

    def iter_raw(self):
        """Iterate over raw object contents.

        :yield: (name, etag, data) tuples
        """
        for (name, etag) in self.iter_with_etag():
            data = self.get_raw(name, etag)
            yield (name, etag, data)

    def iter_calendars(self):
        """Iterate over all calendars.

        :yield: (name, Calendar) tuples
        """
        for (name, etag, data) in self.iter_raw():
            if not name.endswith(ICALENDAR_EXTENSION):
                continue
            yield (name, etag, Calendar.from_ical(b''.join(data)))

    def get_ctag(self):
        """Return the ctag for this store."""
        raise NotImplementedError(self.get_ctag)

    def import_one(self, name, data, replace_etag=None):
        """Import a single object.

        :param name: Name of the object
        :param data: serialized object as bytes
        :param replace_etag: Etag to replace
        :raise NameExists: when the name already exists
        :raise DuplicateUidError: when the uid already exists
        :return: etag
        """
        raise NotImplementedError(self.import_one)

    def delete_one(self, name, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the current
        """
        raise NotImplementedError(self.delete_one)

    def lookup_uid(self, uid):
        """Lookup an item by UID.

        :param uid: UID to look up as string
        :raise KeyError: if no such uid exists
        :return: (name, etag) tuple
        """
        raise NotImplementedError(self.lookup_uid)

    def get_type(self):
        """Get type of this store.

        :return: one of [STORE_TYPE_ADDRESSBOOK, STORE_TYPE_CALENDAR, STORE_TYPE_OTHER]
        """
        ret = STORE_TYPE_OTHER
        for (name, etag) in self.iter_with_etag():
            if name.endswith(ICALENDAR_EXTENSION):
                ret = STORE_TYPE_CALENDAR
            elif name.endswith(VCARD_EXTENSION):
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

    def get_color(Self):
        """Get the color code for this store."""
        raise NotImplementedError(self.get_color)

    def iter_changes(self, old_ctag, new_ctag):
        """Get changes between two versions of this store.

        :param old_ctag: Old ctag (None for empty Store)
        :param new_ctag: New ctag
        :return: Iterator over (name, old_etag, new_etag)
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


class GitStore(Store):
    """A Store backed by a Git Repository.
    """

    def __init__(self, repo, ref=b'refs/heads/master'):
        self.ref = ref
        self.repo = repo
        # Maps uids to (sha, fname)
        self._uid_to_fname = {}
        # Set of blob ids that have already been scanned
        self._fname_to_uid = {}

    def __repr__(self):
        return "%s(%r, ref=%r)" % (type(self).__name__, self.repo, self.ref)

    def lookup_uid(self, uid):
        """Lookup an item by UID.

        :param uid: UID to look up as string
        :raise KeyError: if no such uid exists
        :return: (name, etag) tuple
        """
        self._scan_ids()
        return self._uid_to_fname[uid]

    def _check_duplicate(self, uid, name, replace_etag):
        self._scan_ids()
        if uid is not None:
            try:
                (existing_name, _) = self.lookup_uid(uid)
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

    def get_raw(self, name, etag=None):
        """Get the raw contents of an object.

        :param name: Name of the item
        :param etag: Optional etag
        :return: raw contents as chunks
        """
        if etag is None:
            etag = self._get_etag(name)
        blob = self.repo.object_store[etag.encode('ascii')]
        return blob.chunked

    def _scan_ids(self):
        removed = set(self._fname_to_uid.keys())
        for (name, mode, sha) in self._iterblobs():
            etag = sha.decode('ascii')
            if name in removed:
                removed.remove(name)
            if (name in self._fname_to_uid and
                self._fname_to_uid[name][0] == etag):
                continue
            blob = self.repo.object_store[sha]
            try:
                uid = ExtractUID(name, blob.data)
            except KeyError:
                logger.warning('No UID found in file %s', name)
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
        :yield: (name, etag) tuples
        """
        for (name, mode, sha) in self._iterblobs(ctag):
            yield (name, sha.decode('ascii'))

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Git repository on disk.

        :return: A `GitStore`
        """
        raise NotImplementedError(self.create)

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
        :return: Iterator over (name, old_etag, new_etag)
        """
        if old_ctag is None:
            t = Tree()
            self.repo.object_store.add_object(t)
            old_ctag = t.id.decode('ascii')
        previous = dict(self.iter_with_etag(old_ctag))
        for (name, new_etag) in self.iter_with_etag(new_ctag):
            old_etag = previous.get(name)
            if old_etag != new_etag:
                yield (name, old_etag, new_etag)
            if old_etag is not None:
                del previous[name]
        for (name, old_etag) in previous.items():
            yield (name, old_etag, None)


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

    def _commit_tree(self, tree_id, message):
        try:
            committer = self.repo._get_user_identity()
        except KeyError:
            committer = _DEFAULT_COMMITTER_IDENTITY
        return self.repo.do_commit(message=message, tree=tree_id,
                ref=self.ref, committer=committer)

    def import_one(self, name, data, replace_etag=None):
        """Import a single object.

        :param name: Name of the object
        :param data: serialized object as bytes
        :param etag: optional etag of object to replace
        :raise InvalidETag: when the name already exists but with different etag
        :raise DuplicateUidError: when the uid already exists
        :return: etag
        """
        uid = ExtractUID(name, data)
        self._check_duplicate(uid, name, replace_etag)
        # TODO(jelmer): Verify that 'data' actually represents a valid object
        b = Blob.from_string(data)
        tree = self._get_current_tree()
        name_enc = name.encode(DEFAULT_ENCODING)
        tree[name_enc] = (0o644|stat.S_IFREG, b.id)
        self.repo.object_store.add_objects([(tree, ''), (b, name_enc)])
        self._commit_tree(tree.id, b"Add " + name_enc)
        return b.id.decode('ascii')

    def delete_one(self, name, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the curren
        """
        tree = self._get_current_tree()
        name_enc = name.encode(DEFAULT_ENCODING)
        if not name_enc in tree:
            raise NoSuchItem(name)
        if etag is not None:
            current_sha = tree[name.encode(DEFAULT_ENCODING)][1]
            if current_sha != etag.encode('ascii'):
                raise InvalidETag(name, etag, current_sha.decode('ascii'))
        del tree[name_enc]
        self.repo.object_store.add_objects([(tree, '')])
        self._commit_tree(tree.id, b"Delete " + name_enc)

    @classmethod
    def create(cls, path):
        """Create a new store backed by a Git repository on disk.

        :return: A `GitStore`
        """
        os.mkdir(path)
        return cls(dulwich.repo.Repo.init_bare(path))


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

    def _commit_tree(self, message):
        try:
            committer = self.repo._get_user_identity()
        except KeyError:
            committer = _DEFAULT_COMMITTER_IDENTITY
        return self.repo.do_commit(message=message, committer=committer)

    def import_one(self, name, data, replace_etag=None):
        """Import a single object.

        :param name: name of the object
        :param data: serialized object as bytes
        :param replace_etag: optional etag of object to replace
        :raise InvalidETag: when the name already exists but with different etag
        :raise DuplicateUidError: when the uid already exists
        :return: etag
        """
        uid = ExtractUID(name, data)
        self._check_duplicate(uid, name, replace_etag)
        # TODO(jelmer): Verify that 'data' actually represents a valid object
        p = os.path.join(self.repo.path, name)
        with open(p, 'wb') as f:
            f.write(data)
        self.repo.stage(name)
        etag = self.repo.open_index()[name.encode(DEFAULT_ENCODING)].sha
        message = b'Add ' + name.encode(DEFAULT_ENCODING)
        self._commit_tree(message)
        return etag.decode('ascii')

    def delete_one(self, name, etag=None):
        """Delete an item.

        :param name: Filename to delete
        :param etag: Optional mandatory etag of object to remove
        :raise NoSuchItem: when the item doesn't exist
        :raise InvalidETag: If the specified ETag doesn't match the curren
        """
        p = os.path.join(self.repo.path, name)
        if not os.path.exists(p):
            raise NoSuchItem(name)
        if etag is not None:
            with open(p, 'rb') as f:
                current_etag = Blob.from_string(f.read()).id
            if etag.encode('ascii') != current_etag:
                raise InvalidETag(name, etag, current_etag.decode('ascii'))
        os.unlink(p)
        self.repo.stage(name)
        message = b'Delete ' + name.encode(DEFAULT_ENCODING)
        self._commit_tree(message)

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


def open_store(location):
    """Open store from a location string.

    :param location: Location string to open
    :return: A `Store`
    """
    # For now, just support opening git stores
    return GitStore.open_from_path(location)
