"""Application configuration settings."""

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

