"""Kafka message key models — typed, JSON-serialized keys for every topic.

Every topic in the system uses a Pydantic model for its message key.
This provides:
  - Schema validation on both producer and consumer sides
  - Self-describing keys (source, type, timestamp)
  - Consistent JSON wire format for tooling (kcat, etc.)

Key design principles:
  - **No value fields in keys**: Keys carry routing metadata only.
    Payload data (prices, sizes, etc.) lives exclusively in the message value.
  - **Symbol IS in the value**: While keys include ``symbol`` for partitioning,
    values also carry ``symbol`` for self-describing deserialization.
    Consumers should validate that key.symbol == value.symbol at the boundary.
  - **JSON everywhere**: All keys are serialized as JSON objects, never
    plain strings.  This simplifies ops tooling and schema evolution.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Control-plane key (dev-event topic) ──────────────────────────────────────


class EventKey(BaseModel):
    """Key for all messages on the event topic (``dev-event``, ``prd-event``).

    Used by ``DataRequest``, ``DataReady``, and ``DataError`` messages.
    The ``request_id`` field enables request/reply correlation.
    """

    model_config = ConfigDict(frozen=True)

    event_type: Literal["data_request", "data_ready", "data_error"]
    source: str = ""  # e.g. "smoke_test", "strategy-pcb", "ingestion"
    request_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Market-data key (dev-market-data topic) ──────────────────────────────────


class MarketDataKey(BaseModel):
    """Key for market-data messages (Trade, Quote, Bar).

    Co-locates all data for a given (broker, symbol) pair on the same
    Kafka partition, preserving per-symbol ordering.
    """

    model_config = ConfigDict(frozen=True)

    source: str = "ingestion"
    broker: str = "alpaca"
    symbol: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
