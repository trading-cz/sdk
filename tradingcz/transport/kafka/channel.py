"""Kafka-backed transport implementation.

Uses Confluent's native async API (``AIOConsumer`` / ``AIOProducer``)
for true non-blocking I/O — no thread executors needed.

One ``KafkaChannel`` per topic, one shared ``AIOProducer`` per transport.
All librdkafka parameters are configurable via ``KafkaSettings`` overrides.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from confluent_kafka.aio import AIOConsumer, AIOProducer
from confluent_kafka.admin import AdminClient, NewTopic

from tradingcz.config.settings import KafkaSettings
from tradingcz.transport.protocol import Channel, Message, Transport

logger = logging.getLogger(__name__)


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

        Poll interval is controlled by ``KafkaSettings.consumer_poll_timeout``
        (default 1.0 s).  Override via ``KAFKA_CONSUMER_POLL_TIMEOUT`` env var
        or the ``consumer_overrides`` dict for librdkafka-level tuning.
        """
        group_id = f"{self._settings.consumer_group}-{self._topic}"
        config = self._settings.consumer_config(group_id=group_id)
        consumer = AIOConsumer(config)
        await consumer.subscribe([self._topic])

        try:
            while True:
                msg = await consumer.poll(self._settings.consumer_poll_timeout)
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

    Per-topic configuration overrides are accepted by ``channel()`` and
    fall back to ``KafkaSettings`` defaults when omitted.  This lets the
    config repository (Kustomize/Helm) tune individual topics without
    touching source code.
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

    async def channel(
        self,
        name: str,
        num_partitions: int | None = None,
        replication_factor: int | None = None,
        retention_ms: int | None = None,
        cleanup_policy: str | None = None,
    ) -> Channel:
        """Get or create a Kafka channel for *name*.

        Args:
            name: Kafka topic name.
            num_partitions: Override default partition count.
            replication_factor: Override default replication factor.
            retention_ms: Override default retention in milliseconds.
            cleanup_policy: Override default cleanup policy (``"delete"`` or ``"compact"``).

        All topic-config overrides are optional — when ``None``, the
        ``KafkaSettings`` default is used.  Channels are cached by name,
        so topic config only applies on first call for a given name.
        """
        if name not in self._channels:
            partitions = (
                num_partitions
                if num_partitions is not None
                else self._settings.default_num_partitions
            )
            await self._ensure_topic(
                name,
                num_partitions=partitions,
                replication_factor=replication_factor,
                retention_ms=retention_ms,
                cleanup_policy=cleanup_policy,
            )
            producer = await self._get_producer()
            self._channels[name] = KafkaChannel(name, producer, self._settings)
        return self._channels[name]

    async def _ensure_topic(
        self,
        name: str,
        num_partitions: int,
        replication_factor: int | None = None,
        retention_ms: int | None = None,
        cleanup_policy: str | None = None,
    ) -> None:
        """Create the topic via Admin API if it doesn't already exist.

        Per-topic overrides take precedence over ``KafkaSettings`` defaults.
        """
        if name in self._topics_created:
            return

        loop = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(
            None, lambda: self._admin.list_topics(timeout=10),
        )
        if name in metadata.topics:
            self._topics_created.add(name)
            return

        rf = (
            replication_factor
            if replication_factor is not None
            else self._settings.default_replication_factor
        )
        ret = (
            retention_ms
            if retention_ms is not None
            else self._settings.default_retention_ms
        )
        cp = (
            cleanup_policy
            if cleanup_policy is not None
            else self._settings.default_cleanup_policy
        )

        topic_config: dict[str, str] = {"retention.ms": str(ret)}
        if cp:
            topic_config["cleanup.policy"] = cp

        new_topic = NewTopic(
            name,
            num_partitions=num_partitions,
            replication_factor=rf,
            config=topic_config,
        )
        futures = await loop.run_in_executor(
            None, lambda: self._admin.create_topics([new_topic]),
        )
        for topic, future in futures.items():
            try:
                future.result()
                logger.info(
                    "Created Kafka topic: %s (partitions=%d, rf=%d, retention=%dms)",
                    topic, num_partitions, rf, ret,
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
                logger.debug("AIOProducer.close() not available — skipping")
        self._channels.clear()
