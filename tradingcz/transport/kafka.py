"""Kafka-backed transport implementation.

Uses confluent-kafka with asyncio wrappers.
One KafkaChannel per topic, one shared producer per transport.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from confluent_kafka import Consumer, Producer

from tradingcz.transport.protocol import Channel, Message, Transport

logger = logging.getLogger(__name__)


class KafkaSettings:
    """Kafka connection settings.

    Minimal config object — used by both transport and receiver.
    In production these come from environment-variable-driven Pydantic settings.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        events_topic: str = "event",
        consumer_group: str = "service",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.events_topic = events_topic
        self.consumer_group = consumer_group


class KafkaChannel(Channel):
    """Kafka-backed channel — one topic, fan-out receive.

    Uses a shared producer (from transport) and creates a dedicated
    consumer per ``receive()`` call for fan-out semantics.
    """

    def __init__(self, topic: str, producer: Producer, settings: KafkaSettings) -> None:
        self._topic = topic
        self._producer = producer
        self._settings = settings

    @property
    def name(self) -> str:
        return self._topic

    async def send(self, payload: bytes, *, key: str = "") -> None:
        """Produce a message to the Kafka topic."""
        key_bytes = key.encode() if key else None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._producer.produce(
                self._topic,
                value=payload,
                key=key_bytes,
            ),
        )
        self._producer.poll(0)

    async def receive(self) -> AsyncIterator[Message]:
        """Subscribe and yield messages from this Kafka topic.

        Creates a new consumer with a unique group suffix for fan-out.
        Runs poll in a thread executor to avoid blocking asyncio.
        """
        consumer = Consumer({
            "bootstrap.servers": self._settings.bootstrap_servers,
            "group.id": f"{self._settings.consumer_group}-{self._topic}",
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        consumer.subscribe([self._topic])
        loop = asyncio.get_running_loop()

        try:
            while True:
                msg = await loop.run_in_executor(None, lambda: consumer.poll(1.0))
                if msg is None:
                    continue
                if msg.error():
                    logger.error("Kafka consumer error on %s: %s", self._topic, msg.error())
                    continue
                key = msg.key().decode() if msg.key() else ""
                yield Message(payload=msg.value(), key=key)
        finally:
            consumer.close()

    async def close(self) -> None:
        """No-op — producer lifecycle managed by KafkaTransport."""


class KafkaTransport(Transport):
    """Kafka-backed transport — one shared producer, cached channels."""

    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        self._producer = Producer({
            "bootstrap.servers": settings.bootstrap_servers,
        })
        self._channels: dict[str, KafkaChannel] = {}

    async def channel(self, name: str) -> Channel:
        if name not in self._channels:
            self._channels[name] = KafkaChannel(name, self._producer, self._settings)
        return self._channels[name]

    async def close(self) -> None:
        """Flush producer and close all channels."""
        self._producer.flush(timeout=5.0)
        for ch in self._channels.values():
            await ch.close()
        self._channels.clear()
