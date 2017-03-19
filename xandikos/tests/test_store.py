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

import logging
import os
import tempfile
import shutil
import stat
import unittest

from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from xandikos.icalendar import ICalendarFile
from xandikos.store import (
    GitStore, BareGitStore, TreeGitStore, DuplicateUidError,
    File, InvalidETag, NoSuchItem)

EXAMPLE_VCALENDAR1 = b"""\
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
END:VCALENDAR
"""

EXAMPLE_VCALENDAR2 = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20120314T223512Z
DTSTAMP:20130527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something else
UID:bdc22764-b9e1-42c9-89c2-a85405d8fbff
END:VTODO
END:VCALENDAR
"""

EXAMPLE_VCALENDAR_NO_UID = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN
BEGIN:VTODO
CREATED:20120314T223512Z
DTSTAMP:20130527T221952Z
LAST-MODIFIED:20150314T223512Z
STATUS:NEEDS-ACTION
SUMMARY:do something without uid
END:VTODO
END:VCALENDAR
"""


class BaseStoreTest(object):

    def test_import_one(self):
        gc = self.create_store()
        (name, etag) = gc.import_one('foo.ics', 'text/calendar',
                                     [EXAMPLE_VCALENDAR1])
        self.assertIsInstance(etag, str)
        self.assertEqual([('foo.ics', 'text/calendar', etag)],
                         list(gc.iter_with_etag()))

    def test_import_one_duplicate_uid(self):
        gc = self.create_store()
        (name, etag) = gc.import_one('foo.ics', 'text/calendar',
                                     [EXAMPLE_VCALENDAR1])
        self.assertRaises(
            DuplicateUidError, gc.import_one, 'bar.ics',
            'text/calendar', [EXAMPLE_VCALENDAR1])

    def test_import_one_duplicate_name(self):
        gc = self.create_store()
        (name, etag) = gc.import_one('foo.ics', 'text/calendar',
                                     [EXAMPLE_VCALENDAR1])
        (name, etag) = gc.import_one('foo.ics', 'text/calendar',
                                     [EXAMPLE_VCALENDAR2], replace_etag=etag)
        (name, etag) = gc.import_one('foo.ics', 'text/calendar',
                                     [EXAMPLE_VCALENDAR1])
        self.assertRaises(InvalidETag, gc.import_one, 'foo.ics',
                          'text/calendar', [EXAMPLE_VCALENDAR2],
                          replace_etag='invalidetag')

    def test_get_raw(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one('foo.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one('bar.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR2])
        self.assertEqual(
            EXAMPLE_VCALENDAR1,
            b''.join(gc._get_raw('foo.ics', etag1)))
        self.assertEqual(
            EXAMPLE_VCALENDAR2,
            b''.join(gc._get_raw('bar.ics', etag2)))
        self.assertRaises(
            KeyError,
            gc._get_raw, 'missing.ics', '01' * 20)

    def test_get_file(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one('foo.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR1])
        (name1, etag2) = gc.import_one('bar.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR2])
        f1 = gc.get_file('foo.ics', 'text/calendar', etag1)
        self.assertEqual(EXAMPLE_VCALENDAR1, b''.join(f1.content))
        self.assertEqual('text/calendar', f1.content_type)
        f2 = gc.get_file('bar.ics', 'text/calendar', etag2)
        self.assertEqual(EXAMPLE_VCALENDAR2, b''.join(f2.content))
        self.assertEqual('text/calendar', f2.content_type)
        self.assertRaises(
            KeyError,
            gc._get_raw, 'missing.ics', '01' * 20)

    def test_delete_one(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        (name1, etag1) = gc.import_one('foo.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR1])
        self.assertEqual(
            [('foo.ics', 'text/calendar', etag1)],
            list(gc.iter_with_etag()))
        gc.delete_one('foo.ics')
        self.assertEqual([], list(gc.iter_with_etag()))

    def test_delete_one_with_etag(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        (name1, etag1) = gc.import_one('foo.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR1])
        self.assertEqual(
            [('foo.ics', 'text/calendar', etag1)],
            list(gc.iter_with_etag()))
        gc.delete_one('foo.ics', etag=etag1)
        self.assertEqual([], list(gc.iter_with_etag()))

    def test_delete_one_nonexistant(self):
        gc = self.create_store()
        self.assertRaises(NoSuchItem, gc.delete_one, 'foo.ics')

    def test_delete_one_invalid_etag(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        (name1, etag1) = gc.import_one('foo.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one('bar.ics', 'text/calendar',
                                       [EXAMPLE_VCALENDAR2])
        self.assertEqual(
            set([('foo.ics', 'text/calendar', etag1),
                ('bar.ics', 'text/calendar', etag2)]),
            set(gc.iter_with_etag()))
        self.assertRaises(InvalidETag, gc.delete_one, 'foo.ics', etag=etag2)
        self.assertEqual(
            set([('foo.ics', 'text/calendar', etag1),
                 ('bar.ics', 'text/calendar', etag2)]),
            set(gc.iter_with_etag()))


class BaseGitStoreTest(BaseStoreTest):

    kls = None

    def create_store(self):
        raise NotImplementedError(self.create_store)

    def add_blob(self, gc, name, contents):
        raise NotImplementedError(self.add_blob)

    def test_create(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = self.kls.create(os.path.join(d, 'store'))
        self.assertIsInstance(gc, GitStore)
        self.assertEqual(gc.repo.path, os.path.join(d, 'store'))

    def test_iter_with_etag_missing_uid(self):
        logging.getLogger('').setLevel(logging.ERROR)
        gc = self.create_store()
        bid = self.add_blob(gc, 'foo.ics', EXAMPLE_VCALENDAR_NO_UID)
        self.assertEqual(
            [('foo.ics', 'text/calendar', bid)],
            list(gc.iter_with_etag()))
        gc._scan_uids()
        logging.getLogger('').setLevel(logging.NOTSET)

    def test_iter_with_etag(self):
        gc = self.create_store()
        bid = self.add_blob(gc, 'foo.ics', EXAMPLE_VCALENDAR1)
        self.assertEqual(
            [('foo.ics', 'text/calendar', bid)],
            list(gc.iter_with_etag()))

    def test_get_description(self):
        gc = self.create_store()
        try:
            gc.repo.set_description(b'a repo description')
        except NotImplementedError:
            self.skipTest('old dulwich version without '
                          'MemoryRepo.set_description')
        self.assertEqual(gc.get_description(), 'a repo description')

    def test_displayname(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_color())
        c = gc.repo.get_config()
        c.set(b'xandikos', b'displayname', b'a name')
        if getattr(c, 'path', None):
            c.write_to_path()
        self.assertEqual('a name', gc.get_displayname())

    def test_get_color(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_color())
        c = gc.repo.get_config()
        c.set(b'xandikos', b'color', b'334433')
        if getattr(c, 'path', None):
            c.write_to_path()
        self.assertEqual('334433', gc.get_color())

    def test_default_no_subdirectories(self):
        gc = self.create_store()
        self.assertEqual([], gc.subdirectories())


class GitStoreTest(unittest.TestCase):

    def test_open_from_path_bare(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        Repo.init_bare(d)
        gc = GitStore.open_from_path(d)
        self.assertIsInstance(gc, BareGitStore)
        self.assertEqual(gc.repo.path, d)

    def test_open_from_path_tree(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        Repo.init(d)
        gc = GitStore.open_from_path(d)
        self.assertIsInstance(gc, TreeGitStore)
        self.assertEqual(gc.repo.path, d)


class BareGitStoreTest(BaseGitStoreTest, unittest.TestCase):

    kls = BareGitStore

    def create_store(self):
        store = BareGitStore.create_memory()
        store.load_extra_file_handler(ICalendarFile)
        return store

    def test_create_memory(self):
        gc = BareGitStore.create_memory()
        self.assertIsInstance(gc, GitStore)

    def add_blob(self, gc, name, contents):
        b = Blob.from_string(contents)
        t = Tree()
        t.add(name.encode('utf-8'), 0o644 | stat.S_IFREG, b.id)
        c = Commit()
        c.tree = t.id
        c.committer = c.author = b'Somebody <foo@example.com>'
        c.commit_time = c.author_time = 800000
        c.commit_timezone = c.author_timezone = 0
        c.message = b'do something'
        gc.repo.object_store.add_objects([(b, None), (t, None), (c, None)])
        gc.repo[gc.ref] = c.id
        return b.id.decode('ascii')

    def test_get_ctag(self):
        gc = self.create_store()
        self.assertEqual(Tree().id.decode('ascii'), gc.get_ctag())
        self.add_blob(gc, 'foo.ics', EXAMPLE_VCALENDAR1)
        self.assertEqual(
            gc._get_current_tree().id.decode('ascii'),
            gc.get_ctag())


class TreeGitStoreTest(BaseGitStoreTest, unittest.TestCase):

    kls = TreeGitStore

    def create_store(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        store = self.kls.create(os.path.join(d, 'store'))
        store.load_extra_file_handler(ICalendarFile)
        return store

    def add_blob(self, gc, name, contents):
        with open(os.path.join(gc.repo.path, name), 'wb') as f:
            f.write(contents)
        gc.repo.stage(name.encode('utf-8'))
        return Blob.from_string(contents).id.decode('ascii')


class ExtractRegularUIDTests(unittest.TestCase):

    def test_extract_no_uid(self):
        fi = File([EXAMPLE_VCALENDAR_NO_UID], 'text/bla')
        self.assertRaises(NotImplementedError, fi.get_uid)
