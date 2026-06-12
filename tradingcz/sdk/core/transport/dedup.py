"""Deduplication filter — skip duplicate messages by (source, sequence).

Kafka guarantees at-least-once delivery.  After a consumer restart or
offset reset, messages may be re-delivered.  This filter tracks seen
``(source_app, sequence)`` pairs and skips already-processed messages.

Memory is bounded by *max_size* (default 100k).  When the limit is
reached, the oldest entry is evicted (LRU).

Usage::

    from tradingcz.sdk.core.transport.dedup import DedupFilter
    from tradingcz.sdk.models.headers import Header

    dedup = DedupFilter(max_size=50_000)

    async for msg in channel.receive():
        if dedup.is_duplicate(
            msg.headers.get(Header.SOURCE_APP, ""),
            msg.headers.get(Header.SEQUENCE, "0"),
        ):
            continue
        process(msg)
"""

from collections import OrderedDict


class DedupFilter:
    """Track seen (source_app, sequence) pairs to skip duplicates.

    Sequence numbers are expected to be **globally monotonic per
    (source_app, topic)** — not per symbol or message type.

    Memory is bounded by *max_size* (default 100k).  When the limit is
    reached, the oldest entry is evicted (LRU).
    """

    def __init__(self, max_size: int = 100_000) -> None:
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._max = max_size
        self._hits = 0
        self._total = 0

    def is_duplicate(self, source_app: str, sequence: str) -> bool:
        """Return True if this (source_app, sequence) was already seen.

        Side effect: records the pair as seen if it wasn't already.
        """
        self._total += 1
        key = (source_app, sequence)
        if key in self._seen:
            self._hits += 1
            return True
        self._seen[key] = None
        if len(self._seen) > self._max:
            self._seen.popitem(last=False)  # evict oldest (LRU)
        return False

    def clear(self) -> None:
        """Reset all tracking state."""
        self._seen.clear()
        self._hits = 0
        self._total = 0

    @property
    def skipped_count(self) -> int:
        """Number of duplicates skipped so far."""
        return self._hits

    @property
    def total_count(self) -> int:
        """Total number of messages checked."""
        return self._total


__all__ = ["DedupFilter"]
