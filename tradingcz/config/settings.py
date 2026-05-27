"""Application configuration settings.

Shared settings classes used by ingestion, strategy, and other services.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Network configuration shared across services."""

    model_config = SettingsConfigDict(env_prefix="SERVER_", extra="ignore")
    host: str = Field("127.0.0.1", description="Host to bind")
    port: int = Field(8000, description="Port to bind")


class LoggingSettings(BaseSettings):
    """Application logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")
    level: str = Field("INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")


class KafkaSettings(BaseSettings):
    """Kafka transport configuration.

    Semantic settings (named fields):
        KAFKA_BOOTSTRAP_SERVERS        — broker addresses (default: localhost:9092)
        KAFKA_CONSUMER_GROUP           — consumer group id (default: service)
        KAFKA_DEFAULT_NUM_PARTITIONS   — partitions for auto-created topics (default: 5)
        KAFKA_DEFAULT_REPLICATION_FACTOR — replication for auto-created topics (default: 1)
        KAFKA_DEFAULT_RETENTION_MS     — retention in ms for auto-created topics (default: 5 days)

    librdkafka escape hatches (JSON strings, merged over built-in defaults):
        KAFKA_PRODUCER_OVERRIDES       — e.g. '{"linger.ms": "50", "compression.type": "snappy"}'
        KAFKA_CONSUMER_OVERRIDES       — e.g. '{"fetch.min.bytes": "1000", "auto.offset.reset": "earliest"}'

    The override dicts let you tune any librdkafka parameter from a Kubernetes
    ConfigMap/deployment YAML without touching Python code.
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")

    bootstrap_servers: str = "localhost:9092"
    consumer_group: str = "service"
    default_num_partitions: int = Field(5, description="Default partition count for auto-created topics (env: KAFKA_DEFAULT_NUM_PARTITIONS)")
    default_replication_factor: int = Field(1, description="Default replication factor for auto-created topics (env: KAFKA_DEFAULT_REPLICATION_FACTOR)")
    default_retention_ms: int = Field(432000000, description="Default retention in ms for auto-created topics, 5 days (env: KAFKA_DEFAULT_RETENTION_MS)")

    # librdkafka pass-through — any key/value pair accepted by librdkafka config
    producer_overrides: dict[str, str] = Field(default_factory=dict)
    consumer_overrides: dict[str, str] = Field(default_factory=dict)
