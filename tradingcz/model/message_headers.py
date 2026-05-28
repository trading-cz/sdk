"""Standard message header schemas.

Headers are the primary mechanism for message metadata.  Every Kafka
message carries headers as ``{name: value}`` string pairs.  These
Pydantic models define the expected header fields per topic/pattern.

Key design principles:
  - **Headers = metadata** — message_type, source_app, request_id, schema_version, etc.
  - **Key = routing only** — plain string (e.g. ``"AAPL"``), not JSON.
  - **Value = domain payload** — Pydantic model as JSON, no self-typing.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from tradingcz import SCHEMA_VERSION


class StandardHeaders(BaseModel):
    """Headers present on every Kafka message in the system.

    These are embedded as ``dict[str, str]`` (both key and value are strings).
    The model is used for documentation and validation — at the wire level,
    everything is ``str → str``.
    """

    model_config = ConfigDict(frozen=True)

    message_type: str
    """Type identifier matching a Pydantic model class (e.g. ``"data_request"``)."""

    source_app: str = ""
    """Application that produced this message (e.g. ``"ingestion"``)."""

    schema_version: str = SCHEMA_VERSION
    """Schema version for compatibility checks."""

    sequence: str = "0"
    """Monotonic sequence number per ``(source_app, topic)`` for ordering."""


class EventHeaders(StandardHeaders):
    """Headers for messages on the event topic (``dev-event``).

    Used for DataRequest, DataReady, DataError, ServiceRequest,
    TradingSignal, and other control-plane messages.
    """

    request_id: str = ""
    """Correlation ID for request/reply.  Empty for fire-and-forget."""


class MarketDataHeaders(StandardHeaders):
    """Headers for messages on the market-data topic (``dev-market-data``).

    Used for Trade, Quote, Bar, StreamQuote, and other streaming data.
    """

    source: str = "ingestion"
    """Origin service (e.g. ``"ingestion"``)."""

    broker: str = "alpaca"
    """Broker identifier (e.g. ``"alpaca"``)."""

    symbol: str = ""
    """Ticker symbol (also present as the Kafka message key)."""


class HistoricalHeaders(MarketDataHeaders):
    """Headers for messages on ephemeral historical data topics.

    Adds ``request_id`` for consumer-side filtering.
    Inherits all market-data fields (source, broker, symbol).
    """

    request_id: str = ""
    """Correlation ID linking bars to the originating DataRequest."""


def event_headers(
    *,
    message_type: str,
    source_app: str = "",
    request_id: str = "",
    sequence: int = 0,
) -> dict[str, str]:
    """Build a standard headers dict for an event-topic message.

    Args:
        message_type: e.g. ``"data_request"``, ``"trading_signal"``.
        source_app: Origin app identifier.
        request_id: Correlation ID (empty for fire-and-forget).
        sequence: Monotonic sequence number.

    Returns:
        Headers dict ready to pass to ``KafkaChannel.send(headers=...)``.
    """
    return {
        "message_type": message_type,
        "source_app": source_app,
        "request_id": request_id,
        "schema_version": SCHEMA_VERSION,
        "sequence": str(sequence),
    }


def market_data_headers(
    *,
    message_type: str,
    source: str = "ingestion",
    broker: str = "alpaca",
    symbol: str = "",
    sequence: int = 0,
) -> dict[str, str]:
    """Build a standard headers dict for a market-data message.

    Args:
        message_type: e.g. ``"trade"``, ``"quote"``, ``"bar"``.
        source: Origin service identifier.
        broker: Broker identifier.
        symbol: Ticker symbol.
        sequence: Monotonic sequence number.

    Returns:
        Headers dict ready to pass to ``KafkaChannel.send(headers=...)``.
    """
    return {
        "message_type": message_type,
        "source": source,
        "broker": broker,
        "symbol": symbol,
        "schema_version": SCHEMA_VERSION,
        "sequence": str(sequence),
    }


def historical_headers(
    *,
    source: str = "ingestion",
    broker: str = "alpaca",
    symbol: str = "",
    request_id: str = "",
    sequence: int = 0,
) -> dict[str, str]:
    """Build a standard headers dict for a historical data message.

    Like ``market_data_headers`` but includes ``request_id`` for
    consumer-side filtering on ephemeral historical topics.

    Args:
        source: Origin service identifier.
        broker: Broker identifier.
        symbol: Ticker symbol.
        request_id: Correlation ID from the originating DataRequest.
        sequence: Monotonic sequence number.

    Returns:
        Headers dict ready to pass to ``KafkaChannel.send(headers=...)``.
    """
    return {
        "message_type": "bar",
        "source": source,
        "broker": broker,
        "symbol": symbol,
        "request_id": request_id,
        "schema_version": SCHEMA_VERSION,
        "sequence": str(sequence),
    }


__all__ = [
    "StandardHeaders",
    "EventHeaders",
    "MarketDataHeaders",
    "HistoricalHeaders",
    "event_headers",
    "market_data_headers",
    "historical_headers",
]
