"""ReplayConsumer — typed topic replay for startup state reconstruction.

Replays a Kafka topic from the beginning, yielding typed Pydantic models
until a caller-defined sentinel event is seen.  Built on
:class:`TypedConsumer` (L2) — no manual header parsing or dispatch loops.

Uses a **unique consumer group** (UUID suffix) per replay so every
restart starts from ``earliest``.  Ephemeral groups are auto-cleaned
by Kafka after ``offsets.retention.minutes`` (default 7 days).

The caller publishes a sentinel (e.g. ``LifecycleEventType.INITIALIZING``)
BEFORE starting replay.  The replay stops when it sees that sentinel —
deterministic, no idle-timeout guesswork.

After replay the live :class:`EventRouter` takes over with its own
standard consumer group — no gap: the live group's committed offset
(pre-crash position) is before any messages that arrived during replay.

Usage::

    # 1. Publish sentinel
    await svc.publish_event(
        LifecycleEvent(service_id=svc.service_id, event=LifecycleEventType.INITIALIZING),
        message_type=EventType.SERVICE_LIFECYCLE,
    )

    # 2. Replay until our own INITIALIZING
    consumer = ReplayConsumer(topic, settings)
    async for msg_type, model, raw in consumer.replay(
        types={str(EventType.DATA_REQUEST): DataRequest, ...},
        until=lambda mt, m: (
            mt == str(EventType.SERVICE_LIFECYCLE)
            and m.event == LifecycleEventType.INITIALIZING
        ),
    ):
        reconstruct_state(msg_type, model, raw.headers)

    # 3. Publish READY, start live EventRouter
    await svc.publish_event(
        LifecycleEvent(service_id=svc.service_id, event=LifecycleEventType.READY),
        message_type=EventType.SERVICE_LIFECYCLE,
    )
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel

from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer

logger = logging.getLogger(__name__)


class ReplayConsumer:
    """Replay a topic from the beginning, stopping at a sentinel event.

    Uses a unique consumer group (UUID suffix) with
    ``auto_offset_reset=earliest`` — clean replay on every restart.

    Built on :class:`TypedConsumer` (L2) — typed dispatch +
    deserialization, no manual header parsing.

    Offsets are never committed — the ephemeral group is discarded
    after replay.
    """

    def __init__(self, topic: str, settings: KafkaSettings) -> None:
        self._topic = topic
        self._settings = settings

    async def replay(
        self,
        types: dict[str, type[BaseModel]],
        *,
        until: Callable[[str, BaseModel], bool],
    ) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:

        group_suffix = uuid.uuid4().hex
        logger.info("ReplayConsumer: replaying %s (group_suffix=%s)", self._topic, group_suffix)
        consumer = TypedConsumer(
            topic=self._topic,
            settings=self._settings,
            types=types,
            group_suffix=group_suffix,
            auto_offset_reset="earliest",
            auto_commit=False,
        )
        count = 0
        async for msg_type, model, raw in consumer:
            if until(msg_type, model):
                logger.info("ReplayConsumer: sentinel reached after %d messages — stopping replay", count)
                return
            count += 1
            yield msg_type, model, raw

        logger.info("ReplayConsumer: replay drained — %d messages yielded (no sentinel seen)", count)


__all__ = ["ReplayConsumer"]

