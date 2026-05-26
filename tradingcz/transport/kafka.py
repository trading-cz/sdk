"""Kafka-backed transport implementation.

Uses confluent-kafka with asyncio wrappers.
One KafkaChannel per topic, one shared producer per transport.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic

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
        auto_offset_reset: str = "latest",
        consumer_poll_timeout: float = 1.0,
        default_num_partitions: int = 5,
        default_replication_factor: int = 1,
        default_retention_ms: int = 432000000,
        producer_overrides: dict[str, str] | None = None,
        consumer_overrides: dict[str, str] | None = None,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.events_topic = events_topic
        self.consumer_group = consumer_group
        self.auto_offset_reset = auto_offset_reset
        self.consumer_poll_timeout = consumer_poll_timeout
        self.default_num_partitions = default_num_partitions
        self.default_replication_factor = default_replication_factor
        self.default_retention_ms = default_retention_ms
        self.producer_overrides: dict[str, str] = producer_overrides or {}
        self.consumer_overrides: dict[str, str] = consumer_overrides or {}


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
        """Produce a message to the Kafka topic.

        produce() is a fast local enqueue into librdkafka's internal buffer —
        it never blocks (raises BufferError if queue is full). Calling it
        directly on the asyncio thread is safe and avoids executor overhead.
        poll(0) drains delivery callbacks without blocking.
        Actual network delivery is done by librdkafka's background thread.
        For guaranteed delivery on shutdown, call transport.close().
        """
        key_bytes = key.encode() if key else None
        self._producer.produce(self._topic, value=payload, key=key_bytes)
        self._producer.poll(0)

    async def receive(self) -> AsyncIterator[Message]:
        """Subscribe and yield messages from this Kafka topic.

        Consumer config is built from settings base values merged with
        consumer_overrides, allowing any librdkafka parameter to be tuned
        at runtime via KAFKA_CONSUMER_OVERRIDES env var.
        Runs poll in a thread executor to avoid blocking asyncio.
        """
        base_consumer_config: dict[str, str | bool] = {
            "bootstrap.servers": self._settings.bootstrap_servers,
            "group.id": f"{self._settings.consumer_group}-{self._topic}",
            "auto.offset.reset": self._settings.auto_offset_reset,
            "enable.auto.commit": "true",
        }
        consumer = Consumer({**base_consumer_config, **self._settings.consumer_overrides})
        consumer.subscribe([self._topic])
        loop = asyncio.get_running_loop()
        poll_timeout = self._settings.consumer_poll_timeout

        try:
            while True:
                msg = await loop.run_in_executor(None, lambda: consumer.poll(poll_timeout))
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
    """Kafka-backed transport — one shared producer, cached channels.

    Topics are created on first use via Admin API if they don't already exist,
    ensuring the correct partition count and replication factor.
    """

    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        base_producer_config: dict[str, str] = {
            "bootstrap.servers": settings.bootstrap_servers,
            "linger.ms": "5",  # default: micro-batch window; override via KAFKA_PRODUCER_OVERRIDES
        }
        self._producer = Producer({**base_producer_config, **settings.producer_overrides})
        self._admin = AdminClient({"bootstrap.servers": settings.bootstrap_servers})
        self._channels: dict[str, KafkaChannel] = {}
        self._topics_created: set[str] = set()

    async def channel(self, name: str, num_partitions: int | None = None) -> Channel:
        """Get or create a Kafka channel for *name*.

        If the topic does not exist, it is created with *num_partitions*
        (defaulting to ``settings.default_num_partitions``).
        """
        if name not in self._channels:
            partitions = num_partitions if num_partitions is not None else self._settings.default_num_partitions
            await self._ensure_topic(name, partitions)
            self._channels[name] = KafkaChannel(name, self._producer, self._settings)
        return self._channels[name]

    async def _ensure_topic(self, name: str, num_partitions: int) -> None:
        """Create the topic via Admin API if it doesn't already exist."""
        if name in self._topics_created:
            return
        loop = asyncio.get_running_loop()
        # Check if topic already exists
        metadata = await loop.run_in_executor(None, lambda: self._admin.list_topics(timeout=10))
        if name in metadata.topics:
            self._topics_created.add(name)
            return
        # Create the topic
        new_topic = NewTopic(
            name,
            num_partitions=num_partitions,
            replication_factor=self._settings.default_replication_factor,
            config={"retention.ms": str(self._settings.default_retention_ms)},
        )
        futures = await loop.run_in_executor(
            None,
            lambda: self._admin.create_topics([new_topic]),
        )
        for topic, future in futures.items():
            try:
                future.result()
                logger.info("Created Kafka topic: %s (partitions=%d)", topic, num_partitions)
            except Exception as exc:
                logger.warning("Topic %s may already exist: %s", topic, exc)
        self._topics_created.add(name)

    async def close(self) -> None:
        """Flush producer and close all channels."""
        self._producer.flush(timeout=5.0)
        for ch in self._channels.values():
            await ch.close()
        self._channels.clear()
