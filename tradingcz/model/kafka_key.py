from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class KafkaKey(BaseModel):
    """Lightweight key wrapper for Kafka messages."""

    model_config = ConfigDict(frozen=True)

    source_app: str
    event_type: str
    symbol: str
