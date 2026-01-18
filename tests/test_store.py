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

import logging
import os
import shutil
import stat
import tempfile
import unittest
from zoneinfo import ZoneInfo


from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from xandikos.store import (
    DuplicateUidError,
    File,
    Filter,
    InvalidETag,
    NoSuchItem,
    Store,
)

from xandikos.icalendar import ICalendarFile, CalendarFilter
from xandikos.store.git import BareGitStore, GitStore, TreeGitStore
from xandikos.store.memory import MemoryStore
from xandikos.store.vdir import VdirStore

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

EXAMPLE_VCALENDAR1_NORMALIZED = b"""\
BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN\r
BEGIN:VTODO\r
CREATED:20150314T223512Z\r
DTSTAMP:20150527T221952Z\r
LAST-MODIFIED:20150314T223512Z\r
STATUS:NEEDS-ACTION\r
SUMMARY:do something\r
UID:bdc22720-b9e1-42c9-89c2-a85405d8fbff\r
END:VTODO\r
END:VCALENDAR\r
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

EXAMPLE_VCALENDAR2_NORMALIZED = b"""\
BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//bitfire web engineering//DAVdroid 0.8.0 (ical4j 1.0.x)//EN\r
BEGIN:VTODO\r
CREATED:20120314T223512Z\r
DTSTAMP:20130527T221952Z\r
LAST-MODIFIED:20150314T223512Z\r
STATUS:NEEDS-ACTION\r
SUMMARY:do something else\r
UID:bdc22764-b9e1-42c9-89c2-a85405d8fbff\r
END:VTODO\r
END:VCALENDAR\r
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


class BaseStoreTest:
    def test_import_one(self):
        gc = self.create_store()
        (name, etag) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.assertIsInstance(etag, str)
        self.assertEqual(
            [("foo.ics", "text/calendar", etag)], list(gc.iter_with_etag())
        )

    def test_with_filter(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one("bar.ics", "text/calendar", [EXAMPLE_VCALENDAR2])

        class DummyFilter(Filter):
            content_type = "text/calendar"

            def __init__(self, text) -> None:
                self.text = text

            def check(self, name, resource):
                return self.text in b"".join(resource.content)

        self.assertEqual(
            2, len(list(gc.iter_with_filter(filter=DummyFilter(b"do something"))))
        )

        [(ret_name, ret_file, ret_etag)] = list(
            gc.iter_with_filter(filter=DummyFilter(b"do something else"))
        )
        self.assertEqual(ret_name, name2)
        self.assertEqual(ret_etag, etag2)
        self.assertEqual(ret_file.content_type, "text/calendar")
        self.assertEqual(
            b"".join(ret_file.content),
            EXAMPLE_VCALENDAR2.replace(b"\n", b"\r\n"),
        )

    def test_get_by_index(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one("bar.ics", "text/calendar", [EXAMPLE_VCALENDAR2])
        (name3, etag3) = gc.import_one(
            "bar.txt", "text/plain", [b"Not a calendar file."]
        )
        self.assertEqual({}, dict(gc.index_manager.desired))

        filtertext = "C=VCALENDAR/C=VTODO/P=SUMMARY"

        class DummyFilter(Filter):
            content_type = "text/calendar"

            def __init__(self, text) -> None:
                self.text = text

            def index_keys(self):
                return [[filtertext]]

            def check_from_indexes(self, name, index_values):
                return any(self.text in v for v in index_values[filtertext])

            def check(self, name, resource):
                return self.text in b"".join(resource.content)

        self.assertEqual(
            2, len(list(gc.iter_with_filter(filter=DummyFilter(b"do something"))))
        )

        [(ret_name, ret_file, ret_etag)] = list(
            gc.iter_with_filter(filter=DummyFilter(b"do something else"))
        )
        self.assertEqual({filtertext: 2}, dict(gc.index_manager.desired))

        # Force index
        gc.index.reset([filtertext])

        [(ret_name, ret_file, ret_etag)] = list(
            gc.iter_with_filter(filter=DummyFilter(b"do something else"))
        )
        self.assertEqual({filtertext: 2}, dict(gc.index_manager.desired))

        self.assertEqual(ret_name, name2)
        self.assertEqual(ret_etag, etag2)
        self.assertEqual(ret_file.content_type, "text/calendar")
        self.assertEqual(
            b"".join(ret_file.content),
            EXAMPLE_VCALENDAR2.replace(b"\n", b"\r\n"),
        )

    def test_import_one_duplicate_uid(self):
        gc = self.create_store()
        (name, etag) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.assertRaises(
            DuplicateUidError,
            gc.import_one,
            "bar.ics",
            "text/calendar",
            [EXAMPLE_VCALENDAR1],
        )

    def test_import_one_duplicate_name(self):
        gc = self.create_store()
        (name, etag) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name, etag) = gc.import_one(
            "foo.ics", "text/calendar", [EXAMPLE_VCALENDAR2], replace_etag=etag
        )
        (name, etag) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.assertRaises(
            InvalidETag,
            gc.import_one,
            "foo.ics",
            "text/calendar",
            [EXAMPLE_VCALENDAR2],
            replace_etag="invalidetag",
        )

    def test_get_raw(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one("bar.ics", "text/calendar", [EXAMPLE_VCALENDAR2])
        self.assertEqual(
            EXAMPLE_VCALENDAR1_NORMALIZED,
            b"".join(gc._get_raw("foo.ics", etag1)),
        )
        self.assertEqual(
            EXAMPLE_VCALENDAR2_NORMALIZED,
            b"".join(gc._get_raw("bar.ics", etag2)),
        )
        self.assertRaises(KeyError, gc._get_raw, "missing.ics", "01" * 20)

    def test_get_file(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name1, etag2) = gc.import_one("bar.ics", "text/calendar", [EXAMPLE_VCALENDAR2])
        f1 = gc.get_file("foo.ics", "text/calendar", etag1)
        self.assertEqual(EXAMPLE_VCALENDAR1_NORMALIZED, b"".join(f1.content))
        self.assertEqual("text/calendar", f1.content_type)
        f2 = gc.get_file("bar.ics", "text/calendar", etag2)
        self.assertEqual(EXAMPLE_VCALENDAR2_NORMALIZED, b"".join(f2.content))
        self.assertEqual("text/calendar", f2.content_type)
        self.assertRaises(KeyError, gc._get_raw, "missing.ics", "01" * 20)

    def test_delete_one(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.assertEqual(
            [("foo.ics", "text/calendar", etag1)], list(gc.iter_with_etag())
        )
        gc.delete_one("foo.ics")
        self.assertEqual([], list(gc.iter_with_etag()))

    def test_delete_one_with_etag(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.assertEqual(
            [("foo.ics", "text/calendar", etag1)], list(gc.iter_with_etag())
        )
        gc.delete_one("foo.ics", etag=etag1)
        self.assertEqual([], list(gc.iter_with_etag()))

    def test_delete_one_nonexistant(self):
        gc = self.create_store()
        self.assertRaises(NoSuchItem, gc.delete_one, "foo.ics")

    def test_delete_one_invalid_etag(self):
        gc = self.create_store()
        self.assertEqual([], list(gc.iter_with_etag()))
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one("bar.ics", "text/calendar", [EXAMPLE_VCALENDAR2])
        self.assertEqual(
            {
                ("foo.ics", "text/calendar", etag1),
                ("bar.ics", "text/calendar", etag2),
            },
            set(gc.iter_with_etag()),
        )
        self.assertRaises(InvalidETag, gc.delete_one, "foo.ics", etag=etag2)
        self.assertEqual(
            {
                ("foo.ics", "text/calendar", etag1),
                ("bar.ics", "text/calendar", etag2),
            },
            set(gc.iter_with_etag()),
        )


class VdirStoreTest(BaseStoreTest, unittest.TestCase):
    kls = VdirStore

    def create_store(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        store = self.kls.create(os.path.join(d, "store"))
        store.load_extra_file_handler(ICalendarFile)
        return store


class MemoryStoreTest(BaseStoreTest, unittest.TestCase):
    kls = MemoryStore

    def create_store(self):
        store = self.kls()
        store.load_extra_file_handler(ICalendarFile)
        return store


class BaseGitStoreTest(BaseStoreTest):
    kls: type[Store]

    def create_store(self):
        raise NotImplementedError(self.create_store)

    def add_blob(self, gc, name, contents):
        raise NotImplementedError(self.add_blob)

    def test_create(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = self.kls.create(os.path.join(d, "store"))
        self.assertIsInstance(gc, GitStore)
        self.assertEqual(gc.repo.path, os.path.join(d, "store"))

    def test_iter_with_etag_missing_uid(self):
        logging.getLogger("").setLevel(logging.ERROR)
        gc = self.create_store()
        bid = self.add_blob(gc, "foo.ics", EXAMPLE_VCALENDAR_NO_UID)
        self.assertEqual([("foo.ics", "text/calendar", bid)], list(gc.iter_with_etag()))
        gc._scan_uids()
        logging.getLogger("").setLevel(logging.NOTSET)

    def test_iter_with_etag(self):
        gc = self.create_store()
        bid = self.add_blob(gc, "foo.ics", EXAMPLE_VCALENDAR1)
        self.assertEqual([("foo.ics", "text/calendar", bid)], list(gc.iter_with_etag()))

    def test_get_description_from_git_config(self):
        gc = self.create_store()
        config = gc.repo.get_config()
        config.set(b"xandikos", b"test", b"test")
        if getattr(config, "path", None):
            config.write_to_path()
        gc.repo.set_description(b"a repo description")
        self.assertEqual(gc.get_description(), "a repo description")

    def test_displayname(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_color())
        c = gc.repo.get_config()
        c.set(b"xandikos", b"displayname", b"a name")
        if getattr(c, "path", None):
            c.write_to_path()
        self.assertEqual("a name", gc.get_displayname())

    def test_get_color(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_color())
        c = gc.repo.get_config()
        c.set(b"xandikos", b"color", b"334433")
        if getattr(c, "path", None):
            c.write_to_path()
        self.assertEqual("334433", gc.get_color())

    def test_get_source_url(self):
        gc = self.create_store()
        self.assertIs(None, gc.get_source_url())
        c = gc.repo.get_config()
        c.set(b"xandikos", b"source", b"www.google.com")
        if getattr(c, "path", None):
            c.write_to_path()
        self.assertEqual("www.google.com", gc.get_source_url())

    def test_default_no_subdirectories(self):
        gc = self.create_store()
        self.assertEqual([], gc.subdirectories())

    def test_import_only_once(self):
        gc = self.create_store()
        (name1, etag1) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        (name2, etag2) = gc.import_one("foo.ics", "text/calendar", [EXAMPLE_VCALENDAR1])
        self.assertEqual(name1, name2)
        self.assertEqual(etag1, etag2)
        walker = gc.repo.get_walker(include=[gc.repo.refs[gc.ref]])
        self.assertEqual(1, len([w.commit for w in walker]))


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
        t.add(name.encode("utf-8"), 0o644 | stat.S_IFREG, b.id)
        c = Commit()
        c.tree = t.id
        c.committer = c.author = b"Somebody <foo@example.com>"
        c.commit_time = c.author_time = 800000
        c.commit_timezone = c.author_timezone = 0
        c.message = b"do something"
        gc.repo.object_store.add_objects([(b, None), (t, None), (c, None)])
        gc.repo[gc.ref] = c.id
        return b.id.decode("ascii")

    def test_get_ctag(self):
        gc = self.create_store()
        self.assertEqual(Tree().id.decode("ascii"), gc.get_ctag())
        self.add_blob(gc, "foo.ics", EXAMPLE_VCALENDAR1)
        self.assertEqual(gc._get_current_tree().id.decode("ascii"), gc.get_ctag())


class TreeGitStoreTest(BaseGitStoreTest, unittest.TestCase):
    kls = TreeGitStore

    def create_store(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        store = self.kls.create(os.path.join(d, "store"))
        store.load_extra_file_handler(ICalendarFile)
        return store

    def add_blob(self, gc, name, contents):
        with open(os.path.join(gc.repo.path, name), "wb") as f:
            f.write(contents)
        gc.repo.get_worktree().stage(name.encode("utf-8"))
        return Blob.from_string(contents).id.decode("ascii")


class ExtractRegularUIDTests(unittest.TestCase):
    def test_extract_no_uid(self):
        fi = File([EXAMPLE_VCALENDAR_NO_UID], "text/bla")
        self.assertRaises(NotImplementedError, fi.get_uid)


class ParanoidModeTests(unittest.TestCase):
    """Test for the original issue #235: AssertionError in paranoid mode with index_threshold=0."""

    def test_index_keys_return_type_bug(self):
        """Test that demonstrates the index_keys() return type bug directly."""
        # Create a filter with multiple components/properties to trigger the extend() bug
        filter = CalendarFilter(ZoneInfo("UTC"))
        component_filter = filter.filter_subcomponent("VCALENDAR")
        todo_filter = component_filter.filter_subcomponent("VTODO")
        todo_filter.filter_property("SUMMARY")
        todo_filter.filter_property("CREATED")

        index_keys = filter.index_keys()

        # The fixed code should return a list of lists (AND-list of OR-options)
        # Each inner list represents OR-options for a single AND requirement
        self.assertIsInstance(index_keys, list)
        if index_keys:
            # Each element should be a list of strings (OR-options)
            for key_group in index_keys:
                self.assertIsInstance(
                    key_group,
                    list,
                    f"Expected list of lists, but got list containing {type(key_group)} in {index_keys}",
                )
                for key in key_group:
                    self.assertIsInstance(
                        key,
                        str,
                        f"Expected strings in inner lists, but got {type(key)} in {key_group}",
                    )

        # Expected structure with the fix: [['C=VCALENDAR/C=VTODO/P=SUMMARY'], ['C=VCALENDAR/C=VTODO/P=CREATED']]
        expected_keys = [
            ["C=VCALENDAR/C=VTODO/P=SUMMARY"],
            ["C=VCALENDAR/C=VTODO/P=CREATED"],
        ]
        self.assertEqual(index_keys, expected_keys)

    def test_paranoid_mode_index_threshold_zero(self):
        """Test that reproduces the original AssertionError when using paranoid mode with index_threshold=0.

        This test verifies the fix for: "AssertionError: index based filter not matching real file filter"
        which occurred when double_check_indexes=True and index_threshold=0.
        """
        # Create a temporary store with paranoid mode enabled and index_threshold=0
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)

        store_path = os.path.join(d, "store")
        os.mkdir(store_path)
        repo = Repo.init_bare(store_path)
        repo._autogc_disabled = True

        store = BareGitStore(
            repo,
            double_check_indexes=True,  # Enable paranoid mode
            index_threshold=0,  # Force immediate indexing
        )
        store.load_extra_file_handler(ICalendarFile)

        # Ensure repository is properly closed after test
        self.addCleanup(repo.close)

        # Import a calendar file
        (name, etag) = store.import_one(
            "test.ics", "text/calendar", [EXAMPLE_VCALENDAR1]
        )

        # Create a CalDAV filter that would trigger the bug
        # The old bug happened when index_keys() returned list[str] instead of list[list[str]]
        # causing find_present_keys to iterate over characters instead of keys
        filter = CalendarFilter(ZoneInfo("UTC"))
        component_filter = filter.filter_subcomponent("VCALENDAR")
        todo_filter = component_filter.filter_subcomponent("VTODO")
        todo_filter.filter_property("SUMMARY")

        # Force a scenario that uses the index by pre-indexing and then filtering
        # First, let the filter create some index entries
        results = list(store.iter_with_filter(filter))

        # The old code would sometimes work on first run but fail on subsequent runs
        # when the index state differed. Let's try again to trigger the comparison failure.
        results2 = list(store.iter_with_filter(filter))

        # Verify we get the expected results
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results2), 1)
        result_name, result_file, result_etag = results[0]
        self.assertEqual(result_name, name)
        self.assertEqual(result_etag, etag)
