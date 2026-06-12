"""Kafka wire format — header field names and builders.

- ``Header`` — canonical header key enum
- ``EventHeaders`` — Pydantic model for event-topic headers (no sequence)
- ``DataHeaders`` — Pydantic model for data-topic headers (with sequence for dedup)
- ``KafkaKey`` — Pydantic model for Kafka message keys
- ``make_event_headers()`` — legacy builder (prefer ``EventHeaders`` model)
- ``make_data_headers()`` — legacy builder (prefer ``DataHeaders`` model)
- ``build_event_key()`` — legacy builder (prefer ``KafkaKey.for_event()``)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.models.enums.event import EventType

# ═════════════════════════════════════════════════════════════════════════════
# Header — Kafka header field names
# ═════════════════════════════════════════════════════════════════════════════


class Header(StrEnum):
    """Canonical Kafka header field names."""

    # Universal
    EVENT_TYPE = "event_type"
    SOURCE_APP = "source_app"
    # SCHEMA_VERSION = "schema_version"  # not needed for now

    # Data topics only
    SEQUENCE = "sequence"

    # Event topic only
    REQUEST_ID = "request_id"
    BROKER = "broker"
    SOURCE = "source"


# ═════════════════════════════════════════════════════════════════════════════
# Pydantic header models — type-safe, validated, self-documenting
# ═════════════════════════════════════════════════════════════════════════════


class EventHeaders(BaseModel):
    """Headers for control-plane event-topic messages — no ``sequence`` field.

    Usage::

        headers = EventHeaders(
            event_type=EventType.DATA_REQUEST,
            source_app="ingestion",
            request_id="abc-123",
        )
        await channel.send(payload, key=key, headers=headers.to_kafka())

    Parsing incoming headers::

        parsed = EventHeaders.from_kafka(msg.headers)
        print(parsed.event_type)  # EventType.DATA_REQUEST
    """

    model_config = ConfigDict(extra="allow")

    event_type: EventType
    """Message type — always required."""

    source_app: str = ""
    """Service identifier (e.g. ``"ingestion"``, ``"executor"``)."""

    request_id: str = ""
    """Correlation ID for request/response matching."""

    def to_kafka(self) -> dict[str, str]:
        """Serialize to Kafka wire format (``dict[str, str]``).

        All fields (including extra kwargs) are serialized to string keys.
        """
        d = self.model_dump(exclude_none=True)
        return {k: str(v) for k, v in d.items()}

    @classmethod
    def from_kafka(cls, headers: dict[str, str]) -> EventHeaders:
        """Parse raw Kafka headers into a typed model.

        Unknown fields are preserved (``extra="allow"``).
        """
        return cls(**headers)


class DataHeaders(BaseModel):
    """Headers for data-topic messages — includes ``sequence`` for dedup.

    Usage::

        headers = DataHeaders(
            event_type=EventType.BAR,
            source_app="ingestion",
            broker="alpaca",
            symbol="AAPL",
            sequence=42,
        )
        await channel.send(payload, key="AAPL", headers=headers.to_kafka())
    """

    model_config = ConfigDict(extra="allow")

    event_type: EventType
    """Message type — always required."""

    source_app: str = ""
    """Service identifier."""

    sequence: int = 0
    """Monotonic sequence number for deduplication."""

    broker: str = ""
    """Broker identifier (e.g. ``"alpaca"``)."""

    source: str = ""
    """Source label (defaults to *source_app* if not set)."""

    symbol: str = ""
    """Ticker symbol (e.g. ``"AAPL"``)."""

    request_id: str = ""
    """Correlation ID (set when this data is a response to a request)."""

    def to_kafka(self) -> dict[str, str]:
        """Serialize to Kafka wire format (``dict[str, str]``).

        All fields (including extra kwargs) are serialized to string keys.
        """
        d = self.model_dump(exclude_none=True)
        return {k: str(v) for k, v in d.items()}

    @classmethod
    def from_kafka(cls, headers: dict[str, str]) -> DataHeaders:
        """Parse raw Kafka headers into a typed model.

        Unknown fields are preserved (``extra="allow"``).
        """
        return cls(**headers)


# ═════════════════════════════════════════════════════════════════════════════
# KafkaKey — typed message key
# ═════════════════════════════════════════════════════════════════════════════


class KafkaKey(BaseModel):
    """Kafka message key with factory constructors and serialization.

    Keys are used for partition routing (Murmur2 hash).  Keep them
    simple for even distribution — complex keys hurt performance.

    Usage::

        # Event key: "data_request:ingestion:abc-123"
        key = KafkaKey.for_event(EventType.DATA_REQUEST, "ingestion", "abc-123")
        await channel.send(payload, key=str(key), headers=...)

        # Symbol key: "AAPL"
        key = KafkaKey.for_symbol("AAPL")

        # Custom key
        key = KafkaKey(value="custom-routing-key")
    """

    model_config = ConfigDict(frozen=True)

    value: str
    """The serialized key string."""

    def __str__(self) -> str:
        """Serialize to Kafka wire format (plain string)."""
        return self.value

    @classmethod
    def for_event(
        cls, event_type: EventType, source_app: str, *extra: str
    ) -> KafkaKey:
        """Build a composite event key: ``event_type:source_app[:extra...]``

        Human-readable only — routing is driven by headers, not keys.
        """
        return cls(value=":".join([str(event_type), source_app, *extra]))

    @classmethod
    def for_symbol(cls, symbol: str) -> KafkaKey:
        """Build a symbol-based routing key for per-symbol partitioning."""
        return cls(value=symbol)


# ═════════════════════════════════════════════════════════════════════════════
# Legacy header builders — prefer the Pydantic models above
# ═════════════════════════════════════════════════════════════════════════════


def make_event_headers(
    *,
    event_type: EventType,
    source_app: str = "",
    **extra: str,
) -> dict[str, str]:
    """Build headers for event-topic messages — no ``sequence`` field.

    .. deprecated::
        Prefer :class:`EventHeaders` model for type safety and validation.
    """
    return {
        Header.EVENT_TYPE: str(event_type),
        Header.SOURCE_APP: source_app,
        **extra,
    }


def make_data_headers(
    *,
    event_type: EventType,
    source_app: str = "",
    sequence: int = 0,
    **extra: str,
) -> dict[str, str]:
    """Build headers for data-topic messages — includes ``sequence`` for dedup.

    .. deprecated::
        Prefer :class:`DataHeaders` model for type safety and validation.
    """
    return {
        Header.EVENT_TYPE: str(event_type),
        Header.SOURCE_APP: source_app,
        Header.SEQUENCE: str(sequence),
        **extra,
    }


def build_event_key(event_type: EventType, source_app: str, *extra: str) -> str:
    """Composite Kafka key: ``event_type:source_app[:extra...]``

    .. deprecated::
        Prefer :class:`KafkaKey.for_event` for type safety.
    """
    return ":".join([str(event_type), source_app, *extra])


# ═════════════════════════════════════════════════════════════════════════════
# Backward-compatible alias — prefer the explicit functions above
# ═════════════════════════════════════════════════════════════════════════════

# TODO: remove after all callers migrated to make_event_headers / make_data_headers
make_headers = make_event_headers


__all__ = [
    "Header",
    "EventHeaders",
    "DataHeaders",
    "KafkaKey",
    "build_event_key",
    "make_data_headers",
    "make_event_headers",
    "make_headers",  # backward-compat
]
