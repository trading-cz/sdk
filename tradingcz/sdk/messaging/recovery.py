"""ReplayConsumer — typed topic replay for startup state reconstruction."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from pydantic import BaseModel

from tradingcz.sdk.exceptions import SdkError
from tradingcz.sdk.registry import EventRegistry
from tradingcz.sdk.serialization.json import JsonDeserializer
from tradingcz.sdk.transport.kafka_header import Header
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.transport_consumer import TransportConsumer

logger = logging.getLogger(__name__)


class ReplayConsumer:
    """Replay a topic from its beginning up to its end at the start of the replay."""

    def __init__(self, topic: str, settings: KafkaSettings) -> None:
        self._topic = topic
        self._settings = settings

    async def replay(self, model_types: list[type[BaseModel]]) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:
        """Yield the stored messages of *model_types* in topic order, then stop.

        Messages that arrive after the replay started are left to the live consumer.
        ``EventType`` for each model class is derived from :class:`EventRegistry`.
        """
        types = {str(EventRegistry.event_type_for(m)): m for m in model_types}
        deserializer = JsonDeserializer()
        consumer = TransportConsumer(self._topic, self._settings, uuid.uuid4().hex, auto_offset_reset="earliest", auto_commit=False)
        count = 0
        try:
            end = await consumer.watermarks()
            position = {partition: low for partition, (low, _) in end.items()}
            while any(position[p] < high for p, (_, high) in end.items()):
                for msg in await consumer.poll():
                    position[msg.partition] = msg.offset + 1
                    event_type = msg.headers.get(Header.EVENT_TYPE, "")
                    model_type = types.get(event_type)
                    if model_type is None or msg.offset >= end[msg.partition][1]:
                        continue
                    try:
                        model = deserializer.deserialize(msg.payload, model_type=model_type)
                    except SdkError:
                        logger.warning("ReplayConsumer: skipping unparseable %s at %s[%d] offset %d", event_type, self._topic, msg.partition, msg.offset)
                        continue
                    count += 1
                    yield event_type, model, msg
        finally:
            await consumer.close()
        logger.info("ReplayConsumer: %d messages replayed from %s", count, self._topic)


__all__ = ["ReplayConsumer"]

