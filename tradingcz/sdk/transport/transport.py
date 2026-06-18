"""KafkaTransport — shared Producer, cached channels, topic auto-creation.

One ``KafkaTransport`` per process.  Topics are created on first use
via Admin API if they don't already exist.
"""

import asyncio
import logging

from confluent_kafka import Producer as SyncProducer
from confluent_kafka.admin import AdminClient, NewTopic

from tradingcz.sdk.transport.channel import KafkaChannel
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


class KafkaTransport:
    """Kafka-backed transport — one shared ``Producer``, cached channels.

    Topics are created on first use via Admin API if they don't already exist.
    Per-topic configuration overrides are accepted by ``channel()``.
    """

    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        self._producer: SyncProducer | None = None
        self._admin = AdminClient({"bootstrap.servers": settings.bootstrap_servers})
        self._channels: dict[str, KafkaChannel] = {}
        self._topics_created: set[str] = set()

    def _get_producer(self) -> SyncProducer:
        """Lazy-init the shared synchronous Producer."""
        if self._producer is None:
            self._producer = SyncProducer(self._settings.producer_config())
        return self._producer

    async def channel(
        self,
        name: str,
        num_partitions: int | None = None,
        replication_factor: int | None = None,
        retention_ms: int | None = None,
        cleanup_policy: str | None = None,
    ) -> KafkaChannel:
        """Get or create a Kafka channel for *name*.

        Args:
            name: Kafka topic name.
            num_partitions: Override default partition count.
            replication_factor: Override default replication factor.
            retention_ms: Override default retention in milliseconds.
            cleanup_policy: Override default cleanup policy.

        All overrides are optional — when ``None``, the ``KafkaSettings``
        default is used.  Channels are cached by name, so topic config
        only applies on first call for a given name.
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
            producer = self._get_producer()
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
        """Create the topic via Admin API if it doesn't already exist."""
        if name in self._topics_created:
            return

        loop = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(
            None,
            lambda: self._admin.list_topics(timeout=10),
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
        futures = self._admin.create_topics([new_topic])
        for topic, future in futures.items():
            try:
                future.result()
                logger.info("Created topic '%s'", topic)
            except Exception as exc:
                if "TOPIC_ALREADY_EXISTS" in str(exc):
                    logger.info(
                        "Topic '%s' already exists (race — created by another client)",
                        topic,
                    )
                else:
                    logger.exception("Failed to create topic '%s'", topic)
                    raise

        self._topics_created.add(name)

    async def close(self) -> None:
        """Close all channels and release transport resources.

        Flushes the producer to ensure all queued messages are delivered
        before shutting down.
        """
        if self._producer is not None:
            self._producer.flush(timeout=10)
            self._producer.poll(0)
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
        self._producer = None


__all__ = ["KafkaTransport"]
