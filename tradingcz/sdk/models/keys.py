"""KafkaKey — typed message key with factory constructors."""

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType


class KafkaKey(BaseModel):
    """Typed Kafka message key — used for partition routing (Murmur2 hash).

    Usage::

        key = KafkaKey.for_event(EventType.DATA_REQUEST, "ingestion", "abc-123")
        await channel.send(payload, key=str(key), headers=...)

        key = KafkaKey.for_symbol("AAPL")
        key = KafkaKey.custom("routing-key")
    """

    model_config = ConfigDict(frozen=True)
    value: str = Field(..., description="The serialized key string")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def for_event(cls, event_type: EventType, source_app: str, *extra: str) -> "KafkaKey":
        """Composite key: ``event_type:source_app[:extra...]``"""
        return cls(value=":".join([str(event_type), source_app, *extra]))

    @classmethod
    def for_symbol(cls, symbol: str) -> "KafkaKey":
        """Symbol-based routing key."""
        return cls(value=symbol)

    @classmethod
    def custom(cls, value: str) -> "KafkaKey":
        """Arbitrary custom key."""
        return cls(value=value)


__all__ = ["KafkaKey"]
