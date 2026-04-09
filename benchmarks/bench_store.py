# Xandikos
# Copyright (C) 2025-2026 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Store-level benchmarks for Xandikos.

These target the operations optimised in #611 and are designed to be
comparable across versions (v0.3.0 through HEAD).

Scenarios exercised:
  - Iterating all items in a collection  (iter_with_etag)
  - Looking up a single item by name     (get_etag / get_file_meta)
  - Looking up every item one-by-one     (simulates calendar-multiget)
  - Getting file contents by name        (get_file)

Each scenario is tested against BareGitStore, TreeGitStore and MemoryStore,
with both small (50) and large (500) collections.

Run:
    pytest benchmarks/ --benchmark-enable
    pytest benchmarks/ --benchmark-enable --benchmark-save=<label>
    pytest-benchmark compare <label1> <label2> --sort=fullname
"""

import pytest

from .conftest import (
    LARGE_COLLECTION,
    SMALL_COLLECTION,
    has_get_etag,
    has_get_file_meta,
)


class TestIterWithEtag:
    """Iterate every item in the store.

    This is the hot path for PROPFIND and REPORT requests that enumerate
    an entire collection.
    """

    def test_bare_small(self, benchmark, bare_store_small):
        store, _ = bare_store_small
        result = benchmark(lambda: list(store.iter_with_etag()))
        assert len(result) == SMALL_COLLECTION

    def test_bare_large(self, benchmark, bare_store_large):
        store, _ = bare_store_large
        result = benchmark(lambda: list(store.iter_with_etag()))
        assert len(result) == LARGE_COLLECTION

    def test_tree_small(self, benchmark, tree_store_small):
        store, _ = tree_store_small
        result = benchmark(lambda: list(store.iter_with_etag()))
        assert len(result) == SMALL_COLLECTION

    def test_tree_large(self, benchmark, tree_store_large):
        store, _ = tree_store_large
        result = benchmark(lambda: list(store.iter_with_etag()))
        assert len(result) == LARGE_COLLECTION

    def test_memory_small(self, benchmark, memory_store_small):
        store, _ = memory_store_small
        result = benchmark(lambda: list(store.iter_with_etag()))
        assert len(result) == SMALL_COLLECTION

    def test_memory_large(self, benchmark, memory_store_large):
        store, _ = memory_store_large
        result = benchmark(lambda: list(store.iter_with_etag()))
        assert len(result) == LARGE_COLLECTION


@pytest.mark.skipif(
    not has_get_etag(), reason="get_etag() not available in this version"
)
class TestGetEtagSingle:
    """Look up a single item's etag by name.

    Before v0.3.5 this required a full iter_with_etag() scan;
    after v0.3.5 it is O(1).
    """

    def test_bare_small(self, benchmark, bare_store_small):
        store, etags = bare_store_small
        name = f"event-{SMALL_COLLECTION // 2}.ics"
        result = benchmark(store.get_etag, name)
        assert result == etags[name]

    def test_bare_large(self, benchmark, bare_store_large):
        store, etags = bare_store_large
        name = f"event-{LARGE_COLLECTION // 2}.ics"
        result = benchmark(store.get_etag, name)
        assert result == etags[name]

    def test_tree_small(self, benchmark, tree_store_small):
        store, etags = tree_store_small
        name = f"event-{SMALL_COLLECTION // 2}.ics"
        result = benchmark(store.get_etag, name)
        assert result == etags[name]

    def test_tree_large(self, benchmark, tree_store_large):
        store, etags = tree_store_large
        name = f"event-{LARGE_COLLECTION // 2}.ics"
        result = benchmark(store.get_etag, name)
        assert result == etags[name]

    def test_memory_small(self, benchmark, memory_store_small):
        store, etags = memory_store_small
        name = f"event-{SMALL_COLLECTION // 2}.ics"
        result = benchmark(store.get_etag, name)
        assert result == etags[name]

    def test_memory_large(self, benchmark, memory_store_large):
        store, etags = memory_store_large
        name = f"event-{LARGE_COLLECTION // 2}.ics"
        result = benchmark(store.get_etag, name)
        assert result == etags[name]


def _multiget_via_iter(store, names):
    """Simulate per-item lookup by scanning iter_with_etag for each name.

    This is what the code did before the get_etag/get_file_meta optimisation.
    """
    for name in names:
        for n, ct, etag in store.iter_with_etag():
            if n == name:
                break


def _multiget_via_get_file_meta(store, names):
    """Use the O(1) get_file_meta() path (v0.3.5+)."""
    for name in names:
        store.get_file_meta(name)


class TestMultigetAllItems:
    """Simulate a calendar-multiget that fetches metadata for every item.

    Looks up each item one at a time.  This was the core regression in #611:
    O(n) lookup × n items = O(n²).
    """

    # For versions without get_file_meta we fall back to the iter scan so
    # that we can still measure the baseline.

    def _multiget(self, store, names):
        if has_get_file_meta():
            _multiget_via_get_file_meta(store, names)
        else:
            _multiget_via_iter(store, names)

    def test_bare_small(self, benchmark, bare_store_small):
        store, etags = bare_store_small
        names = list(etags.keys())
        benchmark(self._multiget, store, names)

    def test_bare_large(self, benchmark, bare_store_large):
        store, etags = bare_store_large
        names = list(etags.keys())
        benchmark(self._multiget, store, names)

    def test_tree_small(self, benchmark, tree_store_small):
        store, etags = tree_store_small
        names = list(etags.keys())
        benchmark(self._multiget, store, names)

    def test_tree_large(self, benchmark, tree_store_large):
        store, etags = tree_store_large
        names = list(etags.keys())
        benchmark(self._multiget, store, names)

    def test_memory_small(self, benchmark, memory_store_small):
        store, etags = memory_store_small
        names = list(etags.keys())
        benchmark(self._multiget, store, names)

    def test_memory_large(self, benchmark, memory_store_large):
        store, etags = memory_store_large
        names = list(etags.keys())
        benchmark(self._multiget, store, names)


class TestGetFile:
    """Retrieve the parsed File object for a single item.

    This exercises blob lookup + iCalendar parsing.
    """

    def test_bare_small(self, benchmark, bare_store_small):
        store, etags = bare_store_small
        name = f"event-{SMALL_COLLECTION // 2}.ics"
        etag = etags[name]
        f = benchmark(store.get_file, name, "text/calendar", etag)
        assert f.content_type == "text/calendar"

    def test_bare_large(self, benchmark, bare_store_large):
        store, etags = bare_store_large
        name = f"event-{LARGE_COLLECTION // 2}.ics"
        etag = etags[name]
        f = benchmark(store.get_file, name, "text/calendar", etag)
        assert f.content_type == "text/calendar"

    def test_tree_small(self, benchmark, tree_store_small):
        store, etags = tree_store_small
        name = f"event-{SMALL_COLLECTION // 2}.ics"
        etag = etags[name]
        f = benchmark(store.get_file, name, "text/calendar", etag)
        assert f.content_type == "text/calendar"

    def test_tree_large(self, benchmark, tree_store_large):
        store, etags = tree_store_large
        name = f"event-{LARGE_COLLECTION // 2}.ics"
        etag = etags[name]
        f = benchmark(store.get_file, name, "text/calendar", etag)
        assert f.content_type == "text/calendar"

    def test_memory_small(self, benchmark, memory_store_small):
        store, etags = memory_store_small
        name = f"event-{SMALL_COLLECTION // 2}.ics"
        etag = etags[name]
        f = benchmark(store.get_file, name, "text/calendar", etag)
        assert f.content_type == "text/calendar"

    def test_memory_large(self, benchmark, memory_store_large):
        store, etags = memory_store_large
        name = f"event-{LARGE_COLLECTION // 2}.ics"
        etag = etags[name]
        f = benchmark(store.get_file, name, "text/calendar", etag)
        assert f.content_type == "text/calendar"


class TestMultigetWithFileRetrieval:
    """Simulate a calendar-multiget that fetches actual file content.

    This combines the lookup overhead with file parsing.
    """

    def _fetch_all(self, store, etags):
        for name, etag in etags.items():
            store.get_file(name, "text/calendar", etag)

    def test_bare_small(self, benchmark, bare_store_small):
        store, etags = bare_store_small
        benchmark(self._fetch_all, store, etags)

    def test_bare_large(self, benchmark, bare_store_large):
        store, etags = bare_store_large
        benchmark(self._fetch_all, store, etags)

    def test_tree_small(self, benchmark, tree_store_small):
        store, etags = tree_store_small
        benchmark(self._fetch_all, store, etags)

    def test_tree_large(self, benchmark, tree_store_large):
        store, etags = tree_store_large
        benchmark(self._fetch_all, store, etags)

    def test_memory_small(self, benchmark, memory_store_small):
        store, etags = memory_store_small
        benchmark(self._fetch_all, store, etags)

    def test_memory_large(self, benchmark, memory_store_large):
        store, etags = memory_store_large
        benchmark(self._fetch_all, store, etags)
