"""Kafka wire format — header field names and builders.

- ``Header`` — canonical header key enum
- ``make_event_headers()`` — for event-topic messages (no sequence)
- ``make_data_headers()`` — for data-topic messages (with sequence for dedup)
- ``build_event_key()`` — composite Kafka key for event topic
"""

from __future__ import annotations

from enum import StrEnum

from tradingcz.models.enums.event import EventType

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
# Header builders
# ═════════════════════════════════════════════════════════════════════════════


def make_event_headers(
    *,
    event_type: EventType,
    source_app: str = "",
    **extra: str,
) -> dict[str, str]:
    """Build headers for event-topic messages — no ``sequence`` field.

    Use for: DataRequest, DataReady, ServiceLifecycle, TradingSignal, etc.
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

    Use for: Bar, Quote, Trade, StreamQuote, Snapshot, etc.
    """
    return {
        Header.EVENT_TYPE: str(event_type),
        Header.SOURCE_APP: source_app,
        Header.SEQUENCE: str(sequence),
        **extra,
    }


def build_event_key(event_type: EventType, source_app: str, *extra: str) -> str:
    """Composite Kafka key: ``event_type:source_app[:extra...]``

    Human-readable only — routing is driven by headers, not keys.
    """
    return ":".join([str(event_type), source_app, *extra])


# ═════════════════════════════════════════════════════════════════════════════
# Backward-compatible alias — prefer the explicit functions above
# ═════════════════════════════════════════════════════════════════════════════

# TODO: remove after all callers migrated to make_event_headers / make_data_headers
make_headers = make_event_headers


__all__ = [
    "Header",
    "build_event_key",
    "make_data_headers",
    "make_event_headers",
    "make_headers",  # backward-compat
]
