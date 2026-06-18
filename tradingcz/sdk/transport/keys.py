"""Kafka message keys — typed key builder for Kafka message routing.

Canonical location: ``tradingcz.sdk.transport.keys``.
Also re-exported from ``tradingcz.sdk.models`` for convenience.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType


class KafkaKey(BaseModel):
    """Typed Kafka message key — serialize via ``.to_kafka()`` → str.

    Static factories for common key patterns::

        KafkaKey.for_event(EventType.DATA_REQUEST, "ingestion", "abc-123")
        KafkaKey.for_symbol("AAPL")
        KafkaKey.for_value("custom-key")
    """

    model_config = ConfigDict(frozen=True)
    value: str = Field(..., description="The serialized key string")

    def to_kafka(self) -> str:
        """Serialize to Kafka wire format (plain string)."""
        return self.value

    # ------------------------------------------------------------------
    # Static factories
    # ------------------------------------------------------------------

    @staticmethod
    def for_event(event_type: EventType, source_app: str, *extra: str) -> str:
        """Composite key: ``event_type:source_app[:extra...]`` → str."""
        return KafkaKey(value=":".join([str(event_type), source_app, *extra])).to_kafka()

    @staticmethod
    def for_symbol(symbol: str) -> str:
        """Symbol-based routing key → str."""
        return KafkaKey(value=symbol).to_kafka()

    @staticmethod
    def for_value(value: str) -> str:
        """Arbitrary custom key → str."""
        return KafkaKey(value=value).to_kafka()


__all__ = ["KafkaKey"]
