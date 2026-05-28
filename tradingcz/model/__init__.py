from tradingcz.model.enum import (
    Adjustment,
    OrderSide,
    OrderType,
    SortOrder,
    Timeframe,
)
from tradingcz.model.ingestion import Bar, Quote, Snapshot, StreamQuote, Trade
from tradingcz.model.message_headers import (
    EventHeaders,
    MarketDataHeaders,
    event_headers,
    market_data_headers,
)
from tradingcz.model.events import (
    DataError,
    DataReady,
    DataRequest,
    parse_by_message_type,
    parse_event,
)
from tradingcz.model.signal import (
    SignalEnvelope,
    SignalKey,
    SignalMetadata,
    SignalValue,
    TradingSignal,
    build_signal,
)

# Deprecated aliases for backward compatibility
EventKey = EventHeaders  # type: ignore[assignment]
MarketDataKey = MarketDataHeaders  # type: ignore[assignment]

__all__ = [
    # Enums
    "Timeframe",
    "Adjustment",
    "SortOrder",
    "OrderSide",
    "OrderType",
    # Domain Models
    "Bar",
    "Quote",
    "Trade",
    "Snapshot",
    "StreamQuote",
    # Headers (replaces kafka_key)
    "EventHeaders",
    "MarketDataHeaders",
    "event_headers",
    "market_data_headers",
    # Deprecated aliases
    "EventKey",
    "MarketDataKey",
    # Control-plane events
    "DataRequest",
    "DataReady",
    "DataError",
    "parse_event",
    "parse_by_message_type",
    # Trading signals
    "TradingSignal",
    "SignalKey",
    "SignalValue",
    "SignalMetadata",
    "SignalEnvelope",
    "build_signal",
]
