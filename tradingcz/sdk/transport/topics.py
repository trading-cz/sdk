"""Topic registry — environment-scoped Kafka topic names + admin creation."""

import asyncio
import logging
from dataclasses import dataclass

from confluent_kafka.admin import AdminClient, NewTopic

from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TopicConfig:
    name: str
    partitions: int = 5
    replication_factor: int = 2
    retention_ms: int = 259_200_000  # 3 days
    cleanup_policy: str = "delete"


class TopicRegistry:
    """Environment-scoped topic name registry."""

    def __init__(self, env: str = "dev") -> None:
        self.events = TopicConfig(name=f"{env}-event", partitions=1)
        self.market_data = TopicConfig(name=f"{env}-stock-market-stream-data", partitions=5)
        self.historical_data = TopicConfig(name=f"{env}-stock-market-historical-data", partitions=1)


class TopicAdmin:
    """Creates Kafka topics via Admin API.  Class-level cache prevents duplicate creation."""

    _created: set[str] = set()

    @staticmethod
    async def ensure(
        settings: KafkaSettings,
        name: str,
        *,
        num_partitions: int | None = None,
        replication_factor: int | None = None,
        retention_ms: int | None = None,
        cleanup_policy: str | None = None,
    ) -> None:
        """Create a topic if it doesn't already exist."""
        if name in TopicAdmin._created:
            return

        admin = AdminClient({"bootstrap.servers": settings.bootstrap_servers})
        loop = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(None, lambda: admin.list_topics(timeout=10))
        for topic_name in metadata.topics:
            TopicAdmin._created.add(topic_name)

        if name in TopicAdmin._created:
            return

        partitions = num_partitions if num_partitions is not None else max(1, settings.default_num_partitions)
        rf = replication_factor if replication_factor is not None else settings.default_replication_factor
        ret = retention_ms if retention_ms is not None else settings.default_retention_ms
        cp = cleanup_policy if cleanup_policy is not None else settings.default_cleanup_policy

        topic_config: dict[str, str] = {"retention.ms": str(ret)}
        if cp:
            topic_config["cleanup.policy"] = cp

        new_topic = NewTopic(name, num_partitions=partitions, replication_factor=rf, config=topic_config)
        futures = admin.create_topics([new_topic])
        for topic, future in futures.items():
            try:
                future.result()
                logger.info("Created topic '%s'", topic)
            except Exception as exc:
                if "TOPIC_ALREADY_EXISTS" in str(exc):
                    logger.info("Topic '%s' already exists (race — created by another client)", topic)
                else:
                    logger.exception("Failed to create topic '%s'", topic)
                    raise

        TopicAdmin._created.add(name)

    @staticmethod
    async def ensure_from_config(settings: KafkaSettings, config: TopicConfig) -> None:
        """Create a topic from a :class:`TopicConfig`."""
        await TopicAdmin.ensure(
            settings,
            config.name,
            num_partitions=config.partitions,
            replication_factor=config.replication_factor,
            retention_ms=config.retention_ms,
            cleanup_policy=config.cleanup_policy,
        )
