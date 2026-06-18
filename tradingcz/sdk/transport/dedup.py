"""Deduplication filter — skip duplicate messages by (source, sequence).

Tracks seen (source_app, sequence) pairs. Memory bounded by max_size (LRU eviction).
"""

from collections import OrderedDict


class DedupFilter:
    """Track seen (source_app, sequence) pairs to skip duplicates.

    Sequence numbers are globally monotonic per (source_app, topic).
    Max 100k entries, LRU eviction on overflow.
    """

    def __init__(self, max_size: int = 100_000) -> None:
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._max = max_size
        self._hits = 0
        self._total = 0

    def is_duplicate(self, source_app: str, sequence: str) -> bool:
        """Return True if (source_app, sequence) already seen. Records pair as side effect."""
        self._total += 1
        key = (source_app, sequence)
        if key in self._seen:
            self._hits += 1
            return True
        self._seen[key] = None
        if len(self._seen) > self._max:
            self._seen.popitem(last=False)
        return False

    def clear(self) -> None:
        """Reset tracking state."""
        self._seen.clear()
        self._hits = 0
        self._total = 0

    @property
    def skipped_count(self) -> int:
        """Duplicates skipped."""
        return self._hits

    @property
    def total_count(self) -> int:
        """Total messages checked."""
        return self._total


__all__ = ["DedupFilter"]
