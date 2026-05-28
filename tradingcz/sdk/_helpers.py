"""Internal helpers for the SDK business layer.

These are NOT part of the public API.  They are used internally by
DataClient, SignalPublisher, PositionClient, etc. to avoid code
duplication.

- ``_RequestReply``   — send a typed request, await correlated response
- ``_FireAndForget``  — send a typed message, don't wait
- ``_DedupFilter``    — skip duplicate messages by (source, sequence)
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from tradingcz import SCHEMA_VERSION
from tradingcz.transport.kafka_message import KafkaMessage
from tradingcz.transport.kafka.channel import KafkaChannel

logger = logging.getLogger(__name__)


# ── Deduplication ───────────────────────────────────────────────────────────


class _DedupFilter:
    """Track seen (source_app, sequence) pairs to skip duplicates.

    Kafka guarantees at-least-once delivery.  After a consumer restart
    or offset reset, messages may be re-delivered.  This filter tracks
    seen sequences and skips already-processed messages.

    Sequence numbers are expected to be **globally monotonic per
    (source_app, topic)** — not per symbol or message type.  This
    simplifies dedup at the cost of losing per-symbol gap detection.

    Memory is bounded by *max_size* (default 100k).  When the limit is
    reached, the oldest entry is evicted (LRU).
    """

    def __init__(self, max_size: int = 100_000) -> None:
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._max = max_size
        self._hits = 0   # duplicates skipped
        self._total = 0  # total checked

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


def _extract_dedup_key(msg: KafkaMessage) -> tuple[str, str]:
    """Extract (source, sequence) from a KafkaMessage's headers."""
    source = msg.headers.get("source_app", msg.headers.get("source", ""))
    seq = msg.headers.get("sequence", "0")
    return (source, seq)


class _FireAndForget:
    """Send a typed message on a KafkaChannel.  No response expected.

    Used internally by: SignalPublisher.
    """

    def __init__(self, channel: KafkaChannel, service_id: str) -> None:
        self._channel = channel
        self._service_id = service_id
        self._seq = 0

    async def send(
        self,
        message: BaseModel,
        *,
        message_type: str,
        key: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Serialize *message* to JSON and publish with standard headers.

        Args:
            message: Pydantic model to serialize.
            message_type: Value for the ``message_type`` header (e.g. ``"trading_signal"``).
            key: Kafka message key (empty = no partitioning).
            extra_headers: Additional headers merged into standard set.
        """
        self._seq += 1
        headers: dict[str, str] = {
            "message_type": message_type,
            "source_app": self._service_id,
            "schema_version": SCHEMA_VERSION,
            "sequence": str(self._seq),
        }
        if extra_headers:
            headers.update(extra_headers)

        payload = message.model_dump_json().encode()
        await self._channel.send(payload, key=key, headers=headers)


class _RequestReply:
    """Send a typed request, await a correlated typed response.

    Correlation is by ``request_id`` — both request and response models
    must have a ``request_id: str`` field (convention, not Protocol).

    Used internally by: DataClient, PositionClient, BalanceClient, OrderClient.
    """

    def __init__(
        self,
        channel: KafkaChannel,
        service_id: str,
        *,
        message_types: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self._channel = channel
        self._service_id = service_id
        self._seq = 0
        self._types: dict[str, type[BaseModel]] = dict(message_types) if message_types else {}
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._skipped = 0

    # ------------------------------------------------------------------
    # Type registry
    # ------------------------------------------------------------------

    def register_type(self, message_type: str, model: type[BaseModel]) -> None:
        """Register a message_type → model mapping for response deserialization."""
        self._types[message_type] = model

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background listener (idempotent)."""
        if self._listen_task is not None:
            return
        self._listen_task = asyncio.create_task(self._listen())

    async def close(self) -> None:
        """Cancel listener and reject all pending futures."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def request[Resp: BaseModel](
        self,
        req: BaseModel,
        *,
        response_type: type[Resp],
        request_type: str | None = None,
        timeout: float = 30.0,
    ) -> Resp:
        """Send *req*, await a correlated *Resp*.

        Args:
            req: The request model (must have ``request_id: str``).
            response_type: Expected response Pydantic model class.
            request_type: ``message_type`` header value (auto-inferred if None).
            timeout: Seconds to wait before raising TimeoutError.

        Returns:
            The matched response, typed as *Resp*.

        Raises:
            TimeoutError: No correlated response within *timeout*.
            ValueError: If *req* has no ``request_id`` attribute.
        """
        request_id: str = getattr(req, "request_id", "")
        if not request_id:
            raise ValueError(f"Request model {type(req).__name__} has no request_id")

        mt = request_type or self._infer_type(req)
        self._seq += 1

        payload = req.model_dump_json().encode()
        headers: dict[str, str] = {
            "message_type": mt,
            "source_app": self._service_id,
            "request_id": request_id,
            "schema_version": SCHEMA_VERSION,
            "sequence": str(self._seq),
        }
        await self._channel.send(payload, key="", headers=headers)

        future: asyncio.Future[Resp] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future  # type: ignore[arg-type]

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task: consume channel, dispatch responses by request_id."""
        logger.debug("_RequestReply listener started on %s", self._channel.name)
        try:
            async for msg in self._channel.receive():
                msg_type = msg.headers.get("message_type", "")
                model_type = self._types.get(msg_type)
                if model_type is None:
                    self._skipped += 1
                    continue

                try:
                    parsed = model_type.model_validate_json(msg.payload)
                except Exception:
                    self._skipped += 1
                    continue

                resp_id: str = getattr(parsed, "request_id", "")
                if not resp_id:
                    continue

                future = self._pending.get(resp_id)
                if future is not None and not future.done():
                    future.set_result(parsed)
        except asyncio.CancelledError:
            logger.debug("_RequestReply listener cancelled")
        except Exception:
            logger.exception("_RequestReply listener crashed")

    @property
    def skipped_count(self) -> int:
        """Number of messages skipped (not matching any registered type)."""
        return self._skipped

    @staticmethod
    def _infer_type(model: BaseModel) -> str:
        """Infer message_type from model class name: DataRequest → 'data_request'."""
        import re
        return re.sub(r"(?<!^)(?=[A-Z])", "_", type(model).__name__).lower()
