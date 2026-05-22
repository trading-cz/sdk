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

    Environment variables:
        KAFKA_BOOTSTRAP_SERVERS  — broker addresses (default: localhost:9092)
        KAFKA_EVENTS_TOPIC       — control-plane topic name (default: event)
        KAFKA_CONSUMER_GROUP     — consumer group id (default: service)
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")
    bootstrap_servers: str = "localhost:9092"
    events_topic: str = "event"
    consumer_group: str = "service"
