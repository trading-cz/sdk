"""Kafka message keys — consistent with headers (both have .to_kafka()).

Headers: ``DataHeaders(...).to_kafka()`` → ``dict[str, str]``
Keys:    ``KafkaKey(...).to_kafka()``    → ``str``

Convenience factories return ``str`` directly::

    key = event_key(EventType.DATA_REQUEST, "ingestion", "abc-123")
    key = symbol_key("AAPL")
"""

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType


class KafkaKey(BaseModel):
    """Typed Kafka message key — serialize via ``.to_kafka()`` → str."""

    model_config = ConfigDict(frozen=True)
    value: str = Field(..., description="The serialized key string")

    def to_kafka(self) -> str:
        """Serialize to Kafka wire format (plain string)."""
        return self.value


def event_key(event_type: EventType, source_app: str, *extra: str) -> str:
    """Composite key: ``event_type:source_app[:extra...]`` → str."""
    return KafkaKey(value=":".join([str(event_type), source_app, *extra])).to_kafka()


def symbol_key(symbol: str) -> str:
    """Symbol-based routing key → str."""
    return KafkaKey(value=symbol).to_kafka()


def custom_key(value: str) -> str:
    """Arbitrary custom key → str."""
    return KafkaKey(value=value).to_kafka()


__all__ = ["KafkaKey", "event_key", "symbol_key", "custom_key"]
