"""KafkaKey — typed message key with factory constructors."""

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType


class KafkaKey(BaseModel):
    """Kafka message key — used for partition routing (Murmur2 hash).

    Usage::

        key = KafkaKey.for_event(EventType.DATA_REQUEST, "ingestion", "abc-123")
        await channel.send(payload, key=str(key), headers=...)
    """

    model_config = ConfigDict(frozen=True)
    value: str = Field(..., description="The serialized key string")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def for_event(cls, event_type: EventType, source_app: str, *extra: str) -> "KafkaKey":
        """Build composite key: ``event_type:source_app[:extra...]``"""
        return cls(value=":".join([str(event_type), source_app, *extra]))

    @classmethod
    def for_symbol(cls, symbol: str) -> "KafkaKey":
        """Build symbol-based routing key."""
        return cls(value=symbol)


def build_event_key(event_type: EventType, source_app: str, *extra: str) -> str:
    """Legacy — prefer ``KafkaKey.for_event()``."""
    return ":".join([str(event_type), source_app, *extra])


__all__ = ["KafkaKey", "build_event_key"]
