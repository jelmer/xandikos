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

import tempfile
import shutil
import unittest

from dystros.collection import GitCollection
from dulwich.objects import Blob, Commit, Tree

EXAMPLE_VCALENDAR = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20150314T223512Z
DTSTAMP:20150527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
X-CALYPSO-NAME:bdc22720-b9e1-42c9-89c2-a85405d8fbff.ics
END:VCALENDAR
"""


class GitCollectionTest(unittest.TestCase):

    def test_create_bare(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = GitCollection.create(d, bare=True)
        self.assertIsInstance(gc, GitCollection)
        self.assertEqual(gc.repo.path, d)

    def test_create_nonbare(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = GitCollection.create(d, bare=False)
        self.assertIsInstance(gc, GitCollection)
        self.assertEqual(gc.repo.path, d)

    def test_create_memory(self):
        gc = GitCollection.create_memory()
        self.assertIsInstance(gc, GitCollection)

    def test_iter_with_etag(self):
        gc = GitCollection.create_memory()
        b = Blob.from_string(EXAMPLE_VCALENDAR)
        t = Tree()
        t.add(b'foo.ics', 0o644, b.id)
        c = Commit()
        c.tree = t.id
        c.committer = c.author = b'Somebody <foo@example.com>'
        c.commit_time = c.author_time = 800000
        c.commit_timezone = c.author_timezone = 0
        c.message = b'do something'
        gc.repo.object_store.add_objects([(b, None), (t, None), (c, None)])
        gc.repo[gc.ref] = c.id
        self.assertEqual([(b'foo.ics', b.id)], list(gc.iter_with_etag()))

    def test_get_ctag(self):
        gc = GitCollection.create_memory()
        self.assertEqual(Tree().id, gc.get_ctag())

        b = Blob.from_string(EXAMPLE_VCALENDAR)
        t = Tree()
        t.add(b'foo.ics', 0o644, b.id)
        c = Commit()
        c.tree = t.id
        c.committer = c.author = b'Somebody <foo@example.com>'
        c.commit_time = c.author_time = 800000
        c.commit_timezone = c.author_timezone = 0
        c.message = b'do something'
        gc.repo.object_store.add_objects([(b, None), (t, None), (c, None)])
        gc.repo[gc.ref] = c.id
        self.assertEqual(t.id, gc.get_ctag())
