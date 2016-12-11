# Dystros
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

"""Collections and collection sets."""

from dulwich.objects import Tree
import dulwich.repo


class Collection(object):
    """A ICalendar collection."""

    def iter_with_etag(self):
        """Iterate over all items in the collection with etag.

        :yield: (name, etag) tuples
        """
        raise NotImplementedError(self.iter_with_etag)

    def get_ctag(self):
        """Return the ctag for this collection."""
        raise NotImplementedError(self.get_ctag)


class GitCollection(object):
    """A Collection backed by a Git Repository.
    """

    def __init__(self, repo, ref=b'refs/heads/master'):
        self.ref = ref
        self.repo = repo

    def _get_current_tree(self):
        try:
            ref_object = self.repo[self.ref]
        except KeyError:
            return Tree()
        if isinstance(ref_object, Tree):
            return ref_object
        else:
            return self.repo.object_store[ref_object.tree]

    def get_ctag(self):
        """Return the ctag for this collection."""
        return self._get_current_tree().id

    def iter_with_etag(self):
        """Iterate over all items in the collection with etag.

        :yield: (name, etag) tuples
        """
        tree = self._get_current_tree()
        for (name, mode, sha) in tree.iteritems():
            yield (name, sha)

    @classmethod
    def create(cls, path, bare=True):
        """Create a new collection backed by a Git repository on disk.

        :param bare: Whether to create a bare repository
        :return: A `GitCollection`
        """
        if bare:
            return cls(dulwich.repo.Repo.init_bare(path))
        else:
            return cls(dulwich.repo.Repo.init(path))

    @classmethod
    def create_memory(cls):
        """Create a new collection backed by a memory repository.

        :return: A `GitCollection`
        """
        return cls(dulwich.repo.MemoryRepo())


class CollectionSet(object):
    """A set of ICalendar collections.
    """


class FilesystemCollectionSet(object):
    """A CollectionSet that is backed by a filesystem."""

    def __init__(self, path):
        self._path = path
