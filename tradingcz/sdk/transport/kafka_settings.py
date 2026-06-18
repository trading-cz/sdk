"""Kafka transport configuration.

Semantic settings (named fields) plus librdkafka escape hatches.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Kafka transport — env-driven config with librdkafka escape hatches.

    Key env vars: KAFKA_BOOTSTRAP_SERVERS, KAFKA_CONSUMER_GROUP (required).
    Override any librdkafka param via KAFKA_PRODUCER_OVERRIDES / KAFKA_CONSUMER_OVERRIDES (JSON).
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")

    bootstrap_servers: str = Field("localhost:9092", description="Kafka broker addresses (env: KAFKA_BOOTSTRAP_SERVERS)")
    consumer_group: str = Field(..., description="Consumer group id (env: KAFKA_CONSUMER_GROUP)")
    consumer_poll_timeout: float = Field(1.0, description="Seconds between consumer poll attempts (env: KAFKA_CONSUMER_POLL_TIMEOUT)")
    default_num_partitions: int = Field(5, description="Default partition count for auto-created topics (env: KAFKA_DEFAULT_NUM_PARTITIONS)")
    default_replication_factor: int = Field(1, description="Default replication factor for auto-created topics (env: KAFKA_DEFAULT_REPLICATION_FACTOR)")
    default_retention_ms: int = Field(432000000, description="Default retention in ms for auto-created topics, 5 days (env: KAFKA_DEFAULT_RETENTION_MS)")
    default_cleanup_policy: str = Field("delete", description="Default cleanup policy for auto-created topics (env: KAFKA_DEFAULT_CLEANUP_POLICY)")

    # librdkafka pass-through — any key/value pair accepted by librdkafka config
    producer_overrides: dict[str, str] = Field(default_factory=dict)
    consumer_overrides: dict[str, str] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Config builders
    # ------------------------------------------------------------------

    def producer_config(self) -> dict[str, str]:
        """Build the full producer config (base + overrides).

        Base defaults:
        - linger.ms=5 for micro-batching
        - compression.type=snappy to reduce network payload (critical for
          high-frequency market data streams; halves message size)
        - queue.buffering.max.messages=500000 to handle bursts
        - queue.buffering.max.kbytes=524288 (512 MB) — prevents OOM on
          small VMs while still allowing large bursts
        - message.send.max.retries=10 — caps retries so the queue can
          drain instead of accumulating indefinitely during broker slowdowns.
          librdkafka default is MAX_INT (infinite), which fills the queue
          when the broker is slow → BufferError: Local: Queue full.

        Override via ``KAFKA_PRODUCER_OVERRIDES`` env var
        (e.g. ``{"compression.type": "lz4", "batch.size": "131072"}``).
        """
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
        """Build the full consumer config (base + overrides).

        Callers MUST supply *group_id*.
        All other tuning goes through ``consumer_overrides`` dict
        (e.g. ``{"auto.offset.reset": "earliest", "fetch.min.bytes": "1000"}``).

        Override via ``KAFKA_CONSUMER_OVERRIDES`` env var.
        """
        base: dict[str, str] = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": "true",
        }
        return {**base, **self.consumer_overrides}


__all__ = ["KafkaSettings"]
