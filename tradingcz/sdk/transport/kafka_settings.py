"""Kafka transport configuration — env-driven settings + librdkafka escape hatches."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Kafka transport settings. Key env vars: KAFKA_BOOTSTRAP_SERVERS, KAFKA_CONSUMER_GROUP.

    Override librdkafka params via KAFKA_PRODUCER_OVERRIDES / KAFKA_CONSUMER_OVERRIDES (JSON).
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")

    bootstrap_servers: str = Field(...)
    consumer_group: str = Field(...)
    consumer_poll_timeout_ms: int = Field(500, gt=0)
    consumer_batch_size: int = Field(100, gt=0)
    default_num_partitions: int = Field(5, gt=0)
    default_replication_factor: int = Field(2, gt=1)
    default_retention_ms: int = Field(432000000)  # 5 days
    default_cleanup_policy: str = Field("delete")
    auto_offset_reset: str = Field("latest", pattern="^(earliest|latest|none)$")
    max_poll_interval_ms: int = Field(600_000, gt=0)  # 10 min — prevent rebalance on slow handlers

    producer_overrides: dict[str, str] = Field(default_factory=dict)
    consumer_overrides: dict[str, str] = Field(default_factory=dict)

    def producer_config(self) -> dict[str, str]:
        """Build producer config (base + overrides)."""
        base: dict[str, str] = {
            "bootstrap.servers": self.bootstrap_servers,
            "linger.ms": "5",
            "compression.type": "snappy",
            "queue.buffering.max.messages": "500000",
            "queue.buffering.max.kbytes": "524288",
            "message.send.max.retries": "10",
        }
        return {**base, **self.producer_overrides}

    def consumer_config(self, *, group_id: str) -> dict[str, str]:
        """Build consumer config (base + overrides). Caller must supply group_id."""
        base: dict[str, str] = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": "false",
            "max.poll.interval.ms": str(self.max_poll_interval_ms),
        }
        return {**base, **self.consumer_overrides}


__all__ = ["KafkaSettings"]
