"""Kafka transport configuration.

Semantic settings (named fields) plus librdkafka escape hatches.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Kafka transport configuration.

    Semantic settings (named fields):
        KAFKA_BOOTSTRAP_SERVERS        — broker addresses (REQUIRED, no default)
        KAFKA_CONSUMER_GROUP           — consumer group id (REQUIRED, no default)
        KAFKA_CONSUMER_POLL_TIMEOUT    — seconds between consumer poll attempts (default: 1.0)
        KAFKA_DEFAULT_NUM_PARTITIONS   — partitions for auto-created topics (default: 5)
        KAFKA_DEFAULT_REPLICATION_FACTOR — replication for auto-created topics (default: 1)
        KAFKA_DEFAULT_RETENTION_MS     — retention in ms for auto-created topics (default: 5 days)
        KAFKA_DEFAULT_CLEANUP_POLICY   — cleanup policy for auto-created topics (default: delete)

    librdkafka escape hatches (JSON strings, merged over built-in defaults):
        KAFKA_PRODUCER_OVERRIDES       — e.g. '{"linger.ms": "50", "compression.type": "snappy"}'
        KAFKA_CONSUMER_OVERRIDES       — e.g. '{"fetch.min.bytes": "1000", "auto.offset.reset": "earliest"}'

    The override dicts let you tune any librdkafka parameter from a Kubernetes
    ConfigMap/deployment YAML without touching Python code.
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")

    bootstrap_servers: str = Field(..., description="Kafka broker addresses (env: KAFKA_BOOTSTRAP_SERVERS)")
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
            "auto.offset.reset": "earliest",
            "enable.auto.commit": "true",
        }
        return {**base, **self.consumer_overrides}


__all__ = ["KafkaSettings"]
