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

import logging
import os
import tempfile
import shutil
import stat
import unittest

from icalendar.cal import Calendar

from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from dystros.store import (
    GitStore, BareGitStore, TreeGitStore, DuplicateUidError,
    ExtractCalendarUID, InvalidETag, NoSuchItem,
    logger as store_logger)

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
        etag = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        self.assertIsInstance(etag, str)
        self.assertEqual([('foo.ics', etag)], list(gc.iter_with_etag()))

    def test_import_one_duplicate_uid(self):
        gc = self.create_store()
        etag = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        self.assertRaises(
                DuplicateUidError, gc.import_one, 'bar.ics',
                EXAMPLE_VCALENDAR1)

    def test_import_one_duplicate_name(self):
        gc = self.create_store()
        etag = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        etag = gc.import_one('foo.ics', EXAMPLE_VCALENDAR2, etag)
        etag = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        self.assertRaises(InvalidETag, gc.import_one, 'foo.ics',
                EXAMPLE_VCALENDAR2, 'invalidetag')

    def test_iter_calendars(self):
        gc = self.create_store()
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        etag2 = gc.import_one('bar.ics', EXAMPLE_VCALENDAR2)
        ret = {n: (etag, cal) for (n, etag, cal) in gc.iter_calendars()}
        self.assertEqual(ret,
            {'bar.ics': (etag2, Calendar.from_ical(EXAMPLE_VCALENDAR2)),
             'foo.ics': (etag1, Calendar.from_ical(EXAMPLE_VCALENDAR1)),
             })

    def test_iter_raw(self):
        gc = self.create_store()
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        etag2 = gc.import_one('bar.ics', EXAMPLE_VCALENDAR2)
        ret = {n: (etag, cal) for (n, etag, cal) in gc.iter_raw()}
        self.assertEqual(ret,
            {'bar.ics': (etag2, EXAMPLE_VCALENDAR2),
             'foo.ics': (etag1, EXAMPLE_VCALENDAR1),
             })

    def test_get_raw(self):
        gc = self.create_store()
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        etag2 = gc.import_one('bar.ics', EXAMPLE_VCALENDAR2)
        self.assertEqual(
            EXAMPLE_VCALENDAR1,
            gc.get_raw('foo.ics', etag1))
        self.assertEqual(
            EXAMPLE_VCALENDAR2,
            gc.get_raw('bar.ics', etag2))
        self.assertRaises(
            KeyError,
            gc.get_raw, 'missing.ics', '01' * 20)

    def test_iter_calendars_extension(self):
        gc = self.create_store()
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        etag2 = gc.import_one('bar.txt', EXAMPLE_VCALENDAR2)
        ret = {n: (etag, cal) for (n, etag, cal) in gc.iter_calendars()}
        self.assertEqual(ret,
            {'foo.ics': (etag1, Calendar.from_ical(EXAMPLE_VCALENDAR1))})

    def test_delete_one(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        self.assertEqual([('foo.ics', etag1)], list(gc.iter_with_etag()))
        gc.delete_one('foo.ics')
        self.assertEqual([], list(gc.iter_with_etag()))

    def test_delete_one_with_etag(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        self.assertEqual([('foo.ics', etag1)], list(gc.iter_with_etag()))
        gc.delete_one('foo.ics', etag1)
        self.assertEqual([], list(gc.iter_with_etag()))

    def test_delete_one_nonexistant(self):
        gc = self.create_store()
        self.assertRaises(NoSuchItem, gc.delete_one, 'foo.ics')

    def test_delete_one_invalid_etag(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        etag1 = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        etag2 = gc.import_one('bar.ics', EXAMPLE_VCALENDAR2)
        self.assertEqual(
            set([('foo.ics', etag1), ('bar.ics', etag2)]),
            set(gc.iter_with_etag()))
        self.assertRaises(InvalidETag, gc.delete_one, 'foo.ics', etag2)
        self.assertEqual(
            set([('foo.ics', etag1), ('bar.ics', etag2)]),
            set(gc.iter_with_etag()))

    def test_lookup_uid_nonexistant(self):
        gc = self.create_store()
        self.assertRaises(KeyError, gc.lookup_uid, 'someuid')

    def test_lookup_uid(self):
        gc = self.create_store()
        etag = gc.import_one('foo.ics', EXAMPLE_VCALENDAR1)
        self.assertEqual(
            ('foo.ics', etag),
            gc.lookup_uid('bdc22720-b9e1-42c9-89c2-a85405d8fbff'))


class BaseGitStoreTest(BaseStoreTest):

    kls = None

    def create_store(self):
        raise NotImplementedError(self.create_store)

    def add_blob(self, gc, name, contents):
        raise NotImplementedError(self.add_blob)

    def test_create(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = self.kls.create(d)
        self.assertIsInstance(gc, GitStore)
        self.assertEqual(gc.repo.path, d)

    def test_iter_with_etag_missing_uid(self):
        logging.getLogger('').setLevel(logging.ERROR)
        gc = self.create_store()
        bid = self.add_blob(gc, 'foo.ics', EXAMPLE_VCALENDAR_NO_UID)
        self.assertEqual([('foo.ics', bid)], list(gc.iter_with_etag()))
        gc._scan_ids()
        logging.getLogger('').setLevel(logging.NOTSET)

    def test_iter_with_etag(self):
        gc = self.create_store()
        bid = self.add_blob(gc, 'foo.ics', EXAMPLE_VCALENDAR1)
        self.assertEqual([('foo.ics', bid)], list(gc.iter_with_etag()))
        self.assertEqual(
            ('foo.ics', bid),
            gc.lookup_uid('bdc22720-b9e1-42c9-89c2-a85405d8fbff'))

    def test_get_description(self):
        gc = self.create_store()
        try:
            gc.repo.set_description(b'a repo description')
        except NotImplementedError:
            self.skipTest('old dulwich version without MemoryRepo.set_description')
        self.assertEqual(gc.get_description(), 'a repo description')

    def test_displayname(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_color())
        c = gc.repo.get_config()
        c.set(b'dystros', b'displayname', b'a name')
        if getattr(c, 'path', None):
            c.write_to_path()
        self.assertEqual('a name', gc.get_displayname())

    def test_get_color(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_color())
        c = gc.repo.get_config()
        c.set(b'dystros', b'color', b'334433')
        if getattr(c, 'path', None):
            c.write_to_path()
        self.assertEqual('334433', gc.get_color())


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


class BareGitStoreTest(BaseGitStoreTest,unittest.TestCase):

    kls = BareGitStore

    def create_store(self):
        return BareGitStore.create_memory()

    def test_create_memory(self):
        gc = BareGitStore.create_memory()
        self.assertIsInstance(gc, GitStore)

    def add_blob(self, gc, name, contents):
        b = Blob.from_string(contents)
        t = Tree()
        t.add(name.encode('utf-8'), 0o644|stat.S_IFREG, b.id)
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


class TreeGitStoreTest(BaseGitStoreTest,unittest.TestCase):

    kls = TreeGitStore

    def create_store(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        return self.kls.create(d)

    def add_blob(self, gc, name, contents):
        with open(os.path.join(gc.repo.path, name), 'wb') as f:
            f.write(contents)
        gc.repo.stage(name.encode('utf-8'))
        return Blob.from_string(contents).id.decode('ascii')


class ExtractCalendarUIDTests(unittest.TestCase):

    def test_extract_str(self):
        self.assertEqual(
            'bdc22720-b9e1-42c9-89c2-a85405d8fbff',
            ExtractCalendarUID(EXAMPLE_VCALENDAR1))

    def test_extract_cal(self):
        cal = Calendar.from_ical(EXAMPLE_VCALENDAR1)
        self.assertEqual(
            'bdc22720-b9e1-42c9-89c2-a85405d8fbff',
            ExtractCalendarUID(cal))

    def test_extract_no_uid(self):
        self.assertRaises(
            KeyError,
            ExtractCalendarUID, EXAMPLE_VCALENDAR_NO_UID)
