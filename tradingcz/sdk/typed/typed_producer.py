"""TypedProducer — publish typed Pydantic models via TransportProducer (Layer 2).

Layer 2 does pure type conversion: ``BaseModel``↔``bytes``,
``KafkaKey``↔``str``, ``KafkaHeaders``↔``dict[str, str]``.
No business logic — key and headers are mandatory, built by the caller (Layer 3).

See ``typed/_README.md`` for usage examples.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from tradingcz.sdk.serialization.json import JsonSerializer
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.transport.headers import KafkaHeaders
from tradingcz.sdk.transport.keys import KafkaKey

logger = logging.getLogger(__name__)


class TypedProducer:
    """Layer 2 typed producer — Pydantic models → Kafka topic.

    Pure type conversion: serializes the model, converts key/headers
    to wire format, dispatches to the producer.  No auto-inference.
    """

    def __init__(self, producer: TransportProducer, topic: str) -> None:
        self._producer = producer
        self._topic = topic
        self._serializer: JsonSerializer = JsonSerializer()

    @property
    def producer(self) -> TransportProducer:
        return self._producer

    async def send(
        self,
        value: BaseModel,
        *,
        key: KafkaKey,
        headers: KafkaHeaders,
    ) -> None:
        """Publish a typed model to Kafka.

        Args:
            value: Pydantic model to publish.
            key: Kafka message key (mandatory).
            headers: Kafka message headers (mandatory).
        """
        payload = self._serializer.serialize(value)
        await self._producer.send(
            self._topic,
            payload,
            key=key.to_kafka(),
            headers=headers.to_headers(),
        )

    async def flush(self) -> None:
        """Wait for all queued messages to be delivered to Kafka."""
        await self._producer.flush()

    async def __aenter__(self) -> TypedProducer:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.flush()


__all__ = ["TypedProducer"]

