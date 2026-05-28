"""Unit tests for tradingcz.transport._dedup.DedupFilter."""

import pytest
from tradingcz.transport._dedup import DedupFilter


class TestDedupFilter:
    """Tests for DedupFilter."""

    def test_first_occurrence_not_duplicate(self) -> None:
        d = DedupFilter()
        assert not d.is_duplicate("ingestion", "1")

    def test_second_occurrence_is_duplicate(self) -> None:
        d = DedupFilter()
        d.is_duplicate("ingestion", "1")
        assert d.is_duplicate("ingestion", "1")

    def test_different_source_not_duplicate(self) -> None:
        d = DedupFilter()
        d.is_duplicate("ingestion", "1")
        assert not d.is_duplicate("strategy", "1")

    def test_different_sequence_not_duplicate(self) -> None:
        d = DedupFilter()
        d.is_duplicate("ingestion", "1")
        assert not d.is_duplicate("ingestion", "2")

    def test_skipped_count(self) -> None:
        d = DedupFilter()
        d.is_duplicate("a", "1")
        d.is_duplicate("a", "1")  # dup
        d.is_duplicate("a", "2")
        d.is_duplicate("a", "1")  # dup
        assert d.skipped_count == 2

    def test_total_count(self) -> None:
        d = DedupFilter()
        d.is_duplicate("a", "1")
        d.is_duplicate("a", "1")  # dup
        d.is_duplicate("a", "2")
        assert d.total_count == 3

    def test_clear_resets_state(self) -> None:
        d = DedupFilter()
        d.is_duplicate("a", "1")
        d.is_duplicate("a", "1")  # dup
        d.clear()
        assert d.skipped_count == 0
        assert d.total_count == 0
        assert not d.is_duplicate("a", "1")  # fresh after clear

    def test_lru_eviction(self) -> None:
        d = DedupFilter(max_size=3)
        d.is_duplicate("src", "1")  # key 1
        d.is_duplicate("src", "2")  # key 2
        d.is_duplicate("src", "3")  # key 3
        d.is_duplicate("src", "4")  # key 4, evicts key 1 (oldest)
        # key 1 evicted, so it's no longer a duplicate
        assert not d.is_duplicate("src", "1")

    def test_lru_bumps_on_access(self) -> None:
        """is_duplicate on existing entry should NOT bump LRU order
        (we don't want duplicates to refresh the entry)."""
        d = DedupFilter(max_size=3)
        d.is_duplicate("src", "1")
        d.is_duplicate("src", "2")
        d.is_duplicate("src", "3")
        # Access key 1 again (duplicate)
        d.is_duplicate("src", "1")  # duplicate — doesn't bump LRU
        d.is_duplicate("src", "4")  # evicts oldest = key 1
        # key 1 should still be evicted
        # Actually: current implementation only adds on first occurrence.
        # is_duplicate for existing keys doesn't change LRU order.
        # So key 1 is the oldest and gets evicted.
        assert not d.is_duplicate("src", "1")

    def test_default_max_size(self) -> None:
        d = DedupFilter()
        assert d._max == 100_000

    def test_custom_max_size(self) -> None:
        d = DedupFilter(max_size=500)
        assert d._max == 500

    def test_empty_sequence(self) -> None:
        d = DedupFilter()
        assert not d.is_duplicate("src", "")

    def test_empty_source(self) -> None:
        d = DedupFilter()
        assert not d.is_duplicate("", "1")
