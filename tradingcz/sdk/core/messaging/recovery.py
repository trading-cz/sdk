"""RecoveryReader — one-time topic replay for startup state reconstruction.

Uses a **unique consumer group** per recovery so that every restart
replays from the beginning of the topic.  Kafka's ``auto.offset.reset=earliest``
ensures the consumer starts at the earliest available offset — not offset 0,
which may not exist after topic compaction or test cleanup.

Design rationale
----------------
A unique consumer group (UUID suffix) guarantees a clean slate on every
recovery.  The standard consumer group approach fails because committed
offsets from a previous recovery hide DataRequest events that were sent
before the crash:

1. **First start**: Unique group → ``auto.offset.reset=earliest``
   → replays all available DataRequest events from the topic.
2. **Crash + restart**: Another unique group → same behavior →
   always sees all DataRequest events, not just "new" ones.
3. **Ephemeral groups are harmless**: Consumer groups are lightweight
   in Kafka.  The 7-day ``offsets.retention.minutes`` default cleans
   up stale groups automatically.
4. **No conflict with live consumers**: The application's live
   consumer uses a different group suffix (e.g. ``"stream-health"``),
   so recovery never interferes with ongoing consumption.

Why NOT the standard consumer group?
    - Recovery replays one-time ``DataRequest`` events to rebuild
      in-memory subscription state.  On crash, that state is lost.
      The standard group's committed offset hides old DataRequests,
      so recovery sees 0 messages — and starts with 0 symbols.
    - A unique group per recovery is the correct pattern for
      **state reconstruction** from a log of one-time events.

Usage::

    reader = RecoveryReader(events_channel, idle_timeout=2.0)
    async for msg_type, model, raw in reader.replay({
        str(EventType.DATA_REQUEST):       DataRequest,
        str(EventType.SERVICE_LIFECYCLE):  ServiceLifecycle,
    }):
        ...  # classify and reconstruct state

    # After recovery, live consumption uses a different group suffix:
    async for raw in events_channel.receive(group_suffix="stream-health"):
        ...  # live consumption
"""

import logging
import uuid
from collections.abc import AsyncIterator

from pydantic import BaseModel

from tradingcz.sdk.core.transport.kafka import KafkaChannel
from tradingcz.sdk.core.transport.message import KafkaMessage
from tradingcz.sdk.models.headers import Header

logger = logging.getLogger(__name__)


class RecoveryReader:  # pylint: disable=too-few-public-methods
    """One-time replay of a Kafka topic for startup state recovery.

    Creates a **unique consumer group** on every ``replay()`` call.
    Because the group has no committed offsets, ``auto.offset.reset=earliest``
    kicks in — the consumer always replays from the earliest available
    offset in the topic, regardless of previous runs or topic cleanup.

    The replay stops after *idle_timeout* consecutive seconds with no
    new messages — interpreted as "topic is caught up".

    The ephemeral consumer group is never reused; Kafka's built-in
    ``offsets.retention.minutes`` (default 7 days) cleans it up.
    """

    def __init__(self, channel: KafkaChannel, idle_timeout: float = 2.0) -> None:
        self._channel = channel
        self._idle_timeout = idle_timeout

    async def replay(
        self,
        types: dict[str, type[BaseModel]],
    ) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:
        """Yield ``(msg_type, model, raw_message)`` from the topic.

        Only message types present in *types* are yielded; others are
        silently skipped.  Messages that fail Pydantic validation are
        logged at DEBUG level and skipped.

        Every call creates a unique consumer group (UUID suffix) so
        that recovery always starts from the earliest available offset
        — ``auto.offset.reset=earliest`` — even after previous runs
        or topic compaction/cleanup.  No prior committed offsets exist
        for a brand-new group.

        Args:
            types: Mapping of ``message_type`` string value to Pydantic
                model class used for deserialization.

        Yields:
            ``(msg_type, parsed_model, raw_kafka_message)`` tuples.
        """
        group_suffix = f"recovery-{uuid.uuid4()}"
        logger.debug(
            "RecoveryReader: replaying %s (group=%s, idle_timeout=%.1fs)",
            self._channel.name,
            group_suffix,
            self._idle_timeout,
        )
        count = 0
        async for raw in self._channel.receive(
            group_suffix=group_suffix,
            idle_timeout=self._idle_timeout,
        ):
            msg_type = raw.headers.get(Header.EVENT_TYPE, "")
            model_cls = types.get(msg_type)
            if model_cls is None:
                continue
            try:
                model = model_cls.model_validate_json(raw.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "RecoveryReader: skip bad payload for %s on %s (offset=%d)",
                    msg_type,
                    self._channel.name,
                    raw.offset,
                )
                continue
            count += 1
            yield msg_type, model, raw
        logger.debug(
            "RecoveryReader: replay done — %d messages yielded on %s",
            count,
            self._channel.name,
        )
