"""Kafka wire format — header names, message types, factory, and dispatch.

Every module that builds or reads Kafka messages MUST use this module.
No string literals for header names or message types anywhere else.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from tradingcz import SCHEMA_VERSION

# ═════════════════════════════════════════════════════════════════════════════
# Header — Kafka header field names
# ═════════════════════════════════════════════════════════════════════════════


class Header(StrEnum):
    """Canonical Kafka header field names.

    Usage::

        headers[Header.MESSAGE_TYPE]  → "message_type"
        msg.headers.get(Header.SOURCE_APP, "")
    """

    MESSAGE_TYPE = "message_type"
    SOURCE_APP = "source_app"
    SCHEMA_VERSION = "schema_version"
    SEQUENCE = "sequence"
    REQUEST_ID = "request_id"
    TRACKING_ID = "tracking_id"
    STRATEGY_ID = "strategy_id"
    SOURCE = "source"
    BROKER = "broker"
    SYMBOL = "symbol"
    LIFECYCLE_EVENT = "lifecycle_event"


# ═════════════════════════════════════════════════════════════════════════════
# MessageType — valid values for the ``message_type`` header
# ═════════════════════════════════════════════════════════════════════════════


class MessageType(StrEnum):
    """Values for the ``message_type`` header — drives deserialization.

    Usage::

        make_headers(message_type=MessageType.DATA_REQUEST, ...)
        model = parse_message(MessageType.DATA_READY, payload)
    """

    # Control-plane (event topic)
    DATA_REQUEST = "data_request"
    DATA_READY = "data_ready"
    DATA_ERROR = "data_error"
    SERVICE_REQUEST = "service_request"
    SERVICE_LIFECYCLE = "service_lifecycle"

    # Service responses (event topic)
    POSITION_RESPONSE = "position_response"
    BALANCE_RESPONSE = "balance_response"
    ORDER_RESPONSE = "order_response"

    # Strategy output (signal topic)
    TRADING_SIGNAL = "trading_signal"

    # Market data (data topics)
    BAR = "bar"
    QUOTE = "quote"
    TRADE = "trade"
    STREAM_QUOTE = "stream_quote"
    SNAPSHOT = "snapshot"
    OPTION_SNAPSHOT = "option_snapshot"


# ═════════════════════════════════════════════════════════════════════════════
# make_headers — build standard headers dict
# ═════════════════════════════════════════════════════════════════════════════


def make_headers(
    *,
    message_type: MessageType,
    source_app: str = "",
    sequence: int = 0,
    schema_version: str = SCHEMA_VERSION,
    **extra: str,
) -> dict[str, str]:
    """Build a standard headers dict for any Kafka message.

    The ``message_type`` parameter MUST be a :class:`MessageType` enum
    value — raw strings are rejected at the type level.  This ensures
    every message carries a known, documented wire type.

    Example::

        h = make_headers(
            message_type=MessageType.DATA_REQUEST,
            source_app="ingestion",
            sequence=42,
            request_id="abc123",
            symbol="AAPL",
        )
        await channel.send(payload, headers=h)
    """
    headers: dict[str, str] = {
        Header.MESSAGE_TYPE: str(message_type),
        Header.SOURCE_APP: source_app,
        Header.SCHEMA_VERSION: schema_version,
        Header.SEQUENCE: str(sequence),
    }
    headers.update(extra)
    return headers


# ═════════════════════════════════════════════════════════════════════════════
# build_event_key — composite Kafka key for human-readable event topics
# ═════════════════════════════════════════════════════════════════════════════


def build_event_key(
    message_type: MessageType,
    source_app: str,
    *extra: str,
) -> str:
    """Build a human-readable composite Kafka key for the event topic.

    Format: ``message_type:source_app[:extra...]``

    Examples::

        >>> build_event_key(MessageType.DATA_REQUEST, "pcb-breakout", "abc123")
        'data_request:pcb-breakout:abc123'

        >>> build_event_key(MessageType.SERVICE_LIFECYCLE, "ingestion", "heartbeat")
        'service_lifecycle:ingestion:heartbeat'

        >>> build_event_key(MessageType.DATA_READY, "ingestion", "abc123")
        'data_ready:ingestion:abc123'

    This key is for human scanning / ``kcat`` grep only — application-level
    routing is driven by headers, never by keys.  The event topic has exactly
    one partition, so keys have no load‑balancing effect.
    """
    parts = [str(message_type), source_app, *extra]
    return ":".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
# Model registry & dispatch (message_type → Pydantic model)
# ═════════════════════════════════════════════════════════════════════════════

_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {}


def _ensure_registry() -> None:
    """Populate the message_type → model mapping on first call (lazy, avoids circular imports)."""
    if _MODEL_BY_TYPE:
        return
    # pylint: disable=import-outside-toplevel
    from tradingcz.models.events import (
        DataError,
        DataReady,
        DataRequest,
        ServiceRequest,
    )
    from tradingcz.models.health import ServiceLifecycle
    from tradingcz.models.market import Bar, Quote, Snapshot, StreamQuote, Trade
    from tradingcz.models.signal import TradingSignal

    _MODEL_BY_TYPE.update(
        {
            MessageType.DATA_REQUEST: DataRequest,
            MessageType.DATA_READY: DataReady,
            MessageType.DATA_ERROR: DataError,
            MessageType.SERVICE_REQUEST: ServiceRequest,
            MessageType.SERVICE_LIFECYCLE: ServiceLifecycle,
            MessageType.TRADING_SIGNAL: TradingSignal,
            MessageType.BAR: Bar,
            MessageType.QUOTE: Quote,
            MessageType.TRADE: Trade,
            MessageType.STREAM_QUOTE: StreamQuote,
            MessageType.SNAPSHOT: Snapshot,
        }
    )


def message_model(message_type: str | MessageType) -> type[BaseModel]:
    """Return the Pydantic model class for a given ``message_type`` header value.

    Raises ``ValueError`` if the message_type is unknown.
    """
    mt = str(message_type)
    _ensure_registry()
    cls = _MODEL_BY_TYPE.get(mt)
    if cls is None:
        raise ValueError(f"Unknown message_type: {mt}")
    return cls


def parse_message(message_type: str | MessageType, payload: bytes) -> BaseModel:
    """Deserialize a Kafka message payload using the model for ``message_type``.

    This is the symmetric counterpart to ``make_headers()`` — one builds
    the envelope, the other reads it.

    Example::

        msg_type = msg.headers[Header.MESSAGE_TYPE]
        event = parse_message(msg_type, msg.payload)
    """
    return message_model(message_type).model_validate_json(payload)


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════

__all__ = [
    "Header",
    "MessageType",
    "build_event_key",
    "make_headers",
    "parse_message",
    "message_model",
]
