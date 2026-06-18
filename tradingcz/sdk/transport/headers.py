"""Kafka wire format — header field names and builders.

- ``Header`` — canonical header key enum
- ``EventHeaders`` — Pydantic model for event-topic headers
- ``DataHeaders`` — Pydantic model for data-topic headers (with sequence for dedup)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType

# ═════════════════════════════════════════════════════════════════════════════
# Header — Kafka header field names
# ═════════════════════════════════════════════════════════════════════════════


class Header(StrEnum):
    """Canonical Kafka header field names."""

    # Universal
    EVENT_TYPE = "event_type"
    SOURCE_APP = "source_app"

    # Data topics only
    SEQUENCE = "sequence"

    # Event topic only
    EVENT_ID = "event_id"
    BROKER = "broker"
    SOURCE = "source"


class EventHeaders(BaseModel):
    """Headers for control-plane event-topic messages — no ``sequence`` field.

    Usage::

        headers = EventHeaders(
            event_type=EventType.DATA_REQUEST,
            source_app="ingestion",
            event_id="abc-123",
        )
        await channel.send(payload, key=key, headers=headers.to_kafka())

    Parsing incoming headers::

        parsed = EventHeaders.from_kafka(msg.headers)
        print(parsed.event_type)  # EventType.DATA_REQUEST
    """

    model_config = ConfigDict(extra="allow")
    event_id: str = Field(..., description="Unique event identifier")
    event_type: EventType = Field(..., description="Type of event")
    source_app: str = Field(..., description="Source application that generated the event")

    def to_kafka(self) -> dict[str, str]:
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
    event_type: EventType = Field(..., description="Type of market data event")

    source_app: str = Field(default="", description="Service identifier")
    sequence: int = Field(default=0, description="Monotonic sequence number for deduplication")
    broker: str = Field(default="", description="Broker identifier (e.g. alpaca)")
    source: str = Field(default="", description="Source label (defaults to source_app if not set)")
    symbol: str = Field(default="", description="Ticker symbol (e.g. AAPL)")
    event_id: str = Field(default="", description="Correlation ID (set when data is a response to a request)")

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


__all__ = [
    "Header",
    "EventHeaders",
    "DataHeaders",
]
