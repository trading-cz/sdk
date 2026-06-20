"""RecoveryReader — one-time topic replay for startup state reconstruction.

Uses a **unique consumer group** per recovery so that every restart
replays from the beginning of the topic.  Kafka's ``auto.offset.reset=earliest``
ensures the consumer starts at the earliest available offset — not offset 0,
which may not exist after topic compaction or test cleanup.

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
        str(EventType.DATA_REQUEST): DataRequest,
        str(EventType.SERVICE_LIFECYCLE): LifecycleEvent,
    }):
        ...  # reconstruct state

    # After recovery, live consumption uses a different group suffix:
    async for raw in events_channel.receive(group_suffix="stream-health"):
        ...  # live consumption
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator

from pydantic import BaseModel

from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.transport_consumer import TransportConsumer
from tradingcz.sdk.transport.kafka_header import Header
from tradingcz.sdk.transport.kafka_message import KafkaMessage

logger = logging.getLogger(__name__)


class RecoveryReader:  # pylint: disable=too-few-public-methods
    """One-time replay of a Kafka topic for startup state recovery.

    Replays until *idle_timeout* seconds of silence, then stops.
    Uses a unique consumer group (UUID suffix) per recovery — guarantees
    a clean replay of all available events from the topic.
    """

    def __init__(self, topic: str, settings: KafkaSettings, idle_timeout: float = 2.0) -> None:
        self._topic = topic
        self._settings = settings
        self._idle_timeout = idle_timeout

    async def replay(
        self,
        types: dict[str, type[BaseModel]],
    ) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:
        group_suffix = uuid.uuid4().hex
        logger.info(
            "RecoveryReader: replaying %s (idle_timeout=%.1fs, group_suffix=%s)",
            self._topic,
            self._idle_timeout,
            group_suffix,
        )
        session = TransportConsumer(self._topic, self._settings, group_suffix, auto_offset_reset="earliest")
        count = 0
        last_msg_at = time.monotonic()
        try:
            while True:
                batch = await session.poll()
                if not batch:
                    if time.monotonic() - last_msg_at >= self._idle_timeout:
                        break  # continuous silence → drained
                    continue
                last_msg_at = time.monotonic()
                for raw in batch:
                    msg_type = raw.headers.get(Header.EVENT_TYPE, "")
                    model_cls = types.get(msg_type)
                    if model_cls is None:
                        continue
                    try:
                        model = model_cls.model_validate_json(raw.payload)
                    except Exception:  # pylint: disable=broad-exception-caught
                        logger.info(
                            "RecoveryReader: skip bad payload for %s on %s (offset=%d)",
                            msg_type,
                            self._channel.name,
                            raw.offset,
                        )
                        continue
                    count += 1
                    yield msg_type, model, raw
        finally:
            await session.close()

        logger.info(
            "RecoveryReader: replay done — %d messages yielded on %s",
            count,
            self._channel.name,
        )

