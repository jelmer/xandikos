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

"""Filter benchmarks for Xandikos.

These benchmark iter_with_filter(), which is the hot path for REPORT
requests.  The filter-index optimisation (deferred parsing) in #611
means items that don't match the index are never parsed — these
benchmarks verify that improvement is maintained.

Scenarios:
  - Time-range filter that matches a small subset
  - Time-range filter that matches nothing (worst case for scanning)
  - Text-match filter on SUMMARY
"""

from datetime import datetime, timezone

from xandikos.icalendar import CalendarFilter


def _make_time_range_filter(start, end):
    """Create a CalendarFilter with a VEVENT time-range."""
    f = CalendarFilter(timezone.utc)
    comp = f.filter_subcomponent("VCALENDAR").filter_subcomponent("VEVENT")
    comp.filter_time_range(start, end)
    return f


def _make_summary_filter(text):
    """Create a CalendarFilter matching SUMMARY text."""
    f = CalendarFilter(timezone.utc)
    comp = f.filter_subcomponent("VCALENDAR").filter_subcomponent("VEVENT")
    comp.filter_property("SUMMARY").filter_text_match(
        text, collation="i;unicode-casemap"
    )
    return f


class TestTimeRangeSmallWindow:
    """REPORT with a time-range that matches ~31 items."""

    def _run(self, store):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 2, 1, tzinfo=timezone.utc)
        filt = _make_time_range_filter(start, end)
        return list(store.iter_with_filter(filt))

    def test_bare_small(self, benchmark, bare_store_small):
        store, _ = bare_store_small
        result = benchmark(self._run, store)
        assert len(result) == 31

    def test_bare_large(self, benchmark, bare_store_large):
        store, _ = bare_store_large
        result = benchmark(self._run, store)
        assert len(result) == 31

    def test_tree_small(self, benchmark, tree_store_small):
        store, _ = tree_store_small
        result = benchmark(self._run, store)
        assert len(result) == 31

    def test_tree_large(self, benchmark, tree_store_large):
        store, _ = tree_store_large
        result = benchmark(self._run, store)
        assert len(result) == 31

    def test_memory_small(self, benchmark, memory_store_small):
        store, _ = memory_store_small
        result = benchmark(self._run, store)
        assert len(result) == 31

    def test_memory_large(self, benchmark, memory_store_large):
        store, _ = memory_store_large
        result = benchmark(self._run, store)
        assert len(result) == 31


class TestTimeRangeNoMatch:
    """REPORT with a time-range that matches zero items.

    This is the worst case for scanning, as every item must be checked.
    """

    def _run(self, store):
        # All events start from 2025-01-01; pick a range well before that
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = datetime(2020, 2, 1, tzinfo=timezone.utc)
        filt = _make_time_range_filter(start, end)
        return list(store.iter_with_filter(filt))

    def test_bare_small(self, benchmark, bare_store_small):
        store, _ = bare_store_small
        result = benchmark(self._run, store)
        assert len(result) == 0

    def test_bare_large(self, benchmark, bare_store_large):
        store, _ = bare_store_large
        result = benchmark(self._run, store)
        assert len(result) == 0

    def test_tree_small(self, benchmark, tree_store_small):
        store, _ = tree_store_small
        result = benchmark(self._run, store)
        assert len(result) == 0

    def test_tree_large(self, benchmark, tree_store_large):
        store, _ = tree_store_large
        result = benchmark(self._run, store)
        assert len(result) == 0

    def test_memory_small(self, benchmark, memory_store_small):
        store, _ = memory_store_small
        result = benchmark(self._run, store)
        assert len(result) == 0

    def test_memory_large(self, benchmark, memory_store_large):
        store, _ = memory_store_large
        result = benchmark(self._run, store)
        assert len(result) == 0


class TestSummaryTextMatch:
    """REPORT filtering on SUMMARY text.

    Matches items whose summary contains 'Event 1'
    (i.e. Event 1, Event 10-19, Event 100-199).
    """

    def _run(self, store):
        filt = _make_summary_filter("Benchmark Event 1")
        return list(store.iter_with_filter(filt))

    def test_bare_small(self, benchmark, bare_store_small):
        store, _ = bare_store_small
        result = benchmark(self._run, store)
        # "Benchmark Event 1", "Benchmark Event 10".."19" = 11 matches in 50
        assert len(result) == 11

    def test_bare_large(self, benchmark, bare_store_large):
        store, _ = bare_store_large
        result = benchmark(self._run, store)
        # 1 + 10 + 100 = 111 matches in 500
        assert len(result) == 111

    def test_tree_small(self, benchmark, tree_store_small):
        store, _ = tree_store_small
        result = benchmark(self._run, store)
        assert len(result) == 11

    def test_tree_large(self, benchmark, tree_store_large):
        store, _ = tree_store_large
        result = benchmark(self._run, store)
        assert len(result) == 111

    def test_memory_small(self, benchmark, memory_store_small):
        store, _ = memory_store_small
        result = benchmark(self._run, store)
        assert len(result) == 11

    def test_memory_large(self, benchmark, memory_store_large):
        store, _ = memory_store_large
        result = benchmark(self._run, store)
        assert len(result) == 111
