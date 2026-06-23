"""TypedProducer — publish Pydantic models via TransportProducer."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel

from tradingcz.sdk.serialization.json import JsonSerializer
from tradingcz.sdk.transport.kafka_header import KafkaHeader
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.transport_producer import TransportProducer

logger = logging.getLogger(__name__)


class TypedProducer:
    """Publish typed models to a Kafka topic.

    One ``TransportProducer`` per process — ``TypedProducer`` instances
    share it.  See ``typed/_README.md`` for usage.
    """
    def __init__(
        self,
        producer: TransportProducer,
        topic: str,
        *,
        auto_flush: bool = True,
        on_error: Callable[[str, int, int, str], None] | None = None,
    ) -> None:
        self._producer = producer
        self._topic = topic
        self._auto_flush = auto_flush
        self._on_error = on_error
        self._serializer: JsonSerializer = JsonSerializer()

    @property
    def producer(self) -> TransportProducer:
        return self._producer

    @property
    def topic(self) -> str:
        """Topic this producer sends to."""
        return self._topic

    async def send(self, value: BaseModel, *, key: KafkaKey, headers: KafkaHeader) -> None:
        payload = self._serializer.serialize(value)
        await self._producer.send(
            self._topic,
            payload,
            key=key.to_kafka(),
            headers=headers.to_headers(),
        )

    async def flush(self) -> None:
        await self._producer.flush()

    async def __aenter__(self) -> TypedProducer:
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._auto_flush:
            await self.flush()


__all__ = ["TypedProducer"]

