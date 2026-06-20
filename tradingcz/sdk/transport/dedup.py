"""Deduplication filter — skip duplicate messages by (source_app, sequence)."""

from __future__ import annotations

import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class DedupFilter:
    """Track seen (source_app, sequence) pairs. LRU eviction at max_size."""

    def __init__(self, max_size: int = 100_000) -> None:
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._max = max_size
        self._hits = 0
        self._total = 0

    def is_duplicate(self, source_app: str, sequence: str) -> bool:
        """Return True if pair already seen; record it as side effect."""
        self._total += 1
        key = (source_app, sequence)
        if key in self._seen:
            self._hits += 1
            if self._hits % 1000 == 1:  # log every 1000th duplicate
                logger.debug(
                    "DedupFilter: skipped=%d total=%d (latest: source=%s seq=%s)",
                    self._hits, self._total, source_app, sequence,
                )
            return True
        self._seen[key] = None
        if len(self._seen) > self._max:
            self._seen.popitem(last=False)
        return False

    def clear(self) -> None:
        """Reset all tracking state."""
        self._seen.clear()
        self._hits = 0
        self._total = 0

    @property
    def skipped_count(self) -> int:
        return self._hits

    @property
    def total_count(self) -> int:
        return self._total


__all__ = ["DedupFilter"]
