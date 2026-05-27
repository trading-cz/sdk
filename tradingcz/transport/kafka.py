"""Kafka-backed transport implementation.

Uses Confluent's native async API (``AIOConsumer`` / ``AIOProducer``)
for true non-blocking I/O — no thread executors needed.

One ``KafkaChannel`` per topic, one shared ``AIOProducer`` per transport.
All librdkafka parameters are configurable via ``KafkaSettings`` overrides.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from confluent_kafka.aio import AIOProducer
from confluent_kafka.admin import AdminClient, NewTopic

from tradingcz.transport.protocol import Channel, Message, Transport

logger = logging.getLogger(__name__)

# We need an async consumer — try the aio module first, fall back.
# AIOConsumer may be in confluent_kafka directly (version-dependent).
try:
    from confluent_kafka.aio import AIOConsumer  # type: ignore[attr-defined]
except ImportError:
    from confluent_kafka import AIOConsumer  # type: ignore[attr-defined, no-redef]


class KafkaSettings:
    """Kafka connection settings — fully configurable.

    Every librdkafka parameter can be tuned via the overrides dicts.
    Base defaults provide sensible production defaults.

    Attributes:
        bootstrap_servers: Comma-separated broker addresses.
        consumer_group: Base consumer group id (topic names are appended).
        default_num_partitions: Partition count for auto-created topics.
        default_replication_factor: Replication factor for auto-created topics.
        default_retention_ms: Retention in ms for auto-created topics.
        producer_overrides: Dict merged on top of base producer config.
        consumer_overrides: Dict merged on top of base consumer config.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        consumer_group: str = "service",
        default_num_partitions: int = 5,
        default_replication_factor: int = 1,
        default_retention_ms: int = 432_000_000,
        producer_overrides: dict[str, str] | None = None,
        consumer_overrides: dict[str, str] | None = None,
        # Deprecated — kept for callers that still pass them (ignored):
        events_topic: str = "",          # pylint: disable=unused-argument
        auto_offset_reset: str = "",     # pylint: disable=unused-argument
        consumer_poll_timeout: float = 0,  # pylint: disable=unused-argument
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.consumer_group = consumer_group
        self.default_num_partitions = default_num_partitions
        self.default_replication_factor = default_replication_factor
        self.default_retention_ms = default_retention_ms
        self.producer_overrides: dict[str, str] = producer_overrides or {}
        self.consumer_overrides: dict[str, str] = consumer_overrides or {}

    def producer_config(self) -> dict[str, str]:
        """Build the full producer config (base + overrides).

        Base defaults include linger.ms=5 for micro-batching.
        Override via ``KAFKA_PRODUCER_OVERRIDES`` env var
        (e.g. ``{"compression.type": "snappy", "batch.size": "65536"}``).
        """
        base: dict[str, str] = {
            "bootstrap.servers": self.bootstrap_servers,
            "linger.ms": "5",
        }
        return {**base, **self.producer_overrides}

    def consumer_config(self, *, group_id: str) -> dict[str, str]:
        """Build the full consumer config (base + overrides).

        Callers MUST supply *group_id*.
        All other tuning goes through ``consumer_overrides`` dict
        (e.g. ``{"auto.offset.reset": "earliest", "fetch.min.bytes": "1000"}``).

        Override via ``KAFKA_CONSUMER_OVERRIDES`` env var.
        """
        base: dict[str, str] = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": "true",
        }
        return {**base, **self.consumer_overrides}


class KafkaChannel(Channel):
    """Kafka-backed channel — one topic, fan-out receive.

    Uses a shared ``AIOProducer`` for sends and creates a dedicated
    ``AIOConsumer`` per ``receive()`` call for fan-out semantics.
    """

    def __init__(
        self,
        topic: str,
        producer: AIOProducer,
        settings: KafkaSettings,
    ) -> None:
        self._topic = topic
        self._producer = producer
        self._settings = settings

    @property
    def name(self) -> str:
        return self._topic

    async def send(self, payload: bytes, *, key: str = "") -> None:
        """Produce a message to the Kafka topic — natively async.

        ``AIOProducer.produce()`` returns a future; awaiting it delivers
        the message asynchronously through librdkafka's event loop.
        No thread executor or poll(0) hack needed.
        """
        key_bytes = key.encode() if key else None
        delivery_future = await self._producer.produce(
            self._topic, value=payload, key=key_bytes,
        )
        await delivery_future

    async def receive(self) -> AsyncIterator[Message]:
        """Subscribe and yield messages — natively async consumer.

        Creates a dedicated ``AIOConsumer`` per call for fan-out.
        Consumer config is fully driven by ``KafkaSettings``:
        base defaults merged with ``consumer_overrides``.
        """
        group_id = f"{self._settings.consumer_group}-{self._topic}"
        config = self._settings.consumer_config(group_id=group_id)
        consumer = AIOConsumer(config)
        await consumer.subscribe([self._topic])

        try:
            while True:
                msg = await consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.error(
                        "Kafka consumer error on %s: %s", self._topic, msg.error(),
                    )
                    continue
                key = msg.key().decode() if msg.key() else ""
                yield Message(payload=msg.value(), key=key)
        finally:
            await consumer.close()

    async def close(self) -> None:
        """No-op — producer lifecycle managed by KafkaTransport."""


class KafkaTransport(Transport):
    """Kafka-backed transport — one shared ``AIOProducer``, cached channels.

    Topics are created on first use via Admin API if they don't already exist.
    """

    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        self._producer: AIOProducer | None = None
        self._admin = AdminClient({"bootstrap.servers": settings.bootstrap_servers})
        self._channels: dict[str, KafkaChannel] = {}
        self._topics_created: set[str] = set()

    async def _get_producer(self) -> AIOProducer:
        """Lazy-init the shared AIOProducer."""
        if self._producer is None:
            self._producer = AIOProducer(self._settings.producer_config())
        return self._producer

    async def channel(self, name: str, num_partitions: int | None = None) -> Channel:
        """Get or create a Kafka channel for *name*."""
        if name not in self._channels:
            partitions = (
                num_partitions
                if num_partitions is not None
                else self._settings.default_num_partitions
            )
            await self._ensure_topic(name, partitions)
            producer = await self._get_producer()
            self._channels[name] = KafkaChannel(name, producer, self._settings)
        return self._channels[name]

    async def _ensure_topic(self, name: str, num_partitions: int) -> None:
        """Create the topic via Admin API if it doesn't already exist."""
        if name in self._topics_created:
            return

        loop = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(
            None, lambda: self._admin.list_topics(timeout=10),
        )
        if name in metadata.topics:
            self._topics_created.add(name)
            return

        new_topic = NewTopic(
            name,
            num_partitions=num_partitions,
            replication_factor=self._settings.default_replication_factor,
            config={"retention.ms": str(self._settings.default_retention_ms)},
        )
        futures = await loop.run_in_executor(
            None, lambda: self._admin.create_topics([new_topic]),
        )
        for topic, future in futures.items():
            try:
                future.result()
                logger.info(
                    "Created Kafka topic: %s (partitions=%d)", topic, num_partitions,
                )
            except Exception as exc:
                logger.warning("Topic %s may already exist: %s", topic, exc)
        self._topics_created.add(name)

    async def close(self) -> None:
        """Flush producer and close all channels."""
        if self._producer is not None:
            await self._producer.flush()
            # AIOProducer.close() is the proper async shutdown
            # (type stubs may not be complete — suppress attr-error)
            try:
                await self._producer.close()  # type: ignore[attr-defined]
            except AttributeError:
                pass
        self._channels.clear()
