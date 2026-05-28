"""Deprecated — use ``tradingcz.model.message_headers`` instead.

``EventKey`` and ``MarketDataKey`` were previously used as JSON-serialized
Kafka message keys.  Metadata has moved to Kafka headers.  Keys are now
plain strings for partition routing.

This module re-exports from ``message_headers`` for backward compatibility.
It will be removed in a future release.
"""

import warnings

from tradingcz.model.message_headers import (  # noqa: F401
    EventHeaders,
    HistoricalHeaders,
    MarketDataHeaders,
    StandardHeaders,
    event_headers,
    historical_headers,
    market_data_headers,
)

warnings.warn(
    "tradingcz.model.kafka_key is deprecated; "
    "use tradingcz.model.message_headers instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Legacy aliases for backward compatibility
EventKey = EventHeaders  # type: ignore[assignment]
MarketDataKey = MarketDataHeaders  # type: ignore[assignment]

__all__ = [
    "EventKey",
    "MarketDataKey",
    "EventHeaders",
    "MarketDataHeaders",
    "HistoricalHeaders",
    "StandardHeaders",
    "event_headers",
    "market_data_headers",
    "historical_headers",
]
