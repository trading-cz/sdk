"""ReplayConsumer — typed topic replay for startup state reconstruction."""

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
    """Replay a topic from the beginning, stopping at a sentinel event."""

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

