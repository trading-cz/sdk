"""TypedProducer — publish typed Pydantic models via TransportProducer (Layer 2).

Layer 2 does pure type conversion: ``BaseModel``↔``bytes``,
``KafkaKey``↔``str``, ``KafkaHeader``↔``dict[str, str]``.
No business logic — key and headers are mandatory, built by the caller (Layer 3).

See ``typed/_README.md`` for usage examples.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from tradingcz.sdk.serialization.json import JsonSerializer
from tradingcz.sdk.transport.kafka_header import KafkaHeader
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.transport_producer import TransportProducer

logger = logging.getLogger(__name__)


class TypedProducer:
    def __init__(
        self,
        producer: TransportProducer,
        topic: str,
        *,
        auto_flush: bool = True,
    ) -> None:
        self._producer = producer
        self._topic = topic
        self._auto_flush = auto_flush
        self._serializer: JsonSerializer = JsonSerializer()

    @property
    def producer(self) -> TransportProducer:
        return self._producer

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

