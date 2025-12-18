"""Trading Model - Shared data models for the trading platform.

This package provides:
- Enums: Timeframe, Adjustment, SortOrder, OrderSide, OrderType
- Domain Models: Bar, Quote, Trade, Snapshot (pure dataclasses)
- Response Models: HTTP responses and Kafka keys
- Serialization: JSON/CSV functions for domain models

Usage:
    from tradingcz.model import Timeframe, Bar, Quote
    from tradingcz.model.response import BarResponse, QuoteResponse
    from tradingcz.model.serde import bar_to_dict, bar_from_dict
"""

from .enums import (
    Timeframe,
    Adjustment,
    SortOrder,
    OrderSide,
    OrderType,
)
from .domain import (
    Bar,
    Quote,
    Trade,
    Snapshot,
)
from .response import (
    BarResponse,
    QuoteResponse,
    TradeResponse,
    SnapshotResponse,
    bar_to_response,
    quote_to_response,
    trade_to_response,
    snapshot_to_response,
    MarketStockQuoteKey,
    MarketStockTradeKey,
    RawSignalKey,
)

from .serde import (
    bar_from_dict,
    bar_from_json,
    bar_to_dict,
    bar_to_json,
    quote_from_dict,
    quote_from_json,
    quote_to_dict,
    quote_to_json,
    trade_from_dict,
    trade_from_json,
    trade_to_dict,
    trade_to_json,
    snapshot_from_dict,
    snapshot_from_json,
    snapshot_to_dict,
    snapshot_to_json,
    bars_from_csv,
    bars_to_csv,
)

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
    # Response Models
    "BarResponse",
    "QuoteResponse",
    "TradeResponse",
    "SnapshotResponse",
    "bar_to_response",
    "quote_to_response",
    "trade_to_response",
    "snapshot_to_response",
    "MarketStockQuoteKey",
    "MarketStockTradeKey",
    "RawSignalKey",
    # Serde
    "bar_to_dict",
    "bar_from_dict",
    "bar_to_json",
    "bar_from_json",
    "quote_to_dict",
    "quote_from_dict",
    "quote_to_json",
    "quote_from_json",
    "trade_to_dict",
    "trade_from_dict",
    "trade_to_json",
    "trade_from_json",
    "snapshot_to_dict",
    "snapshot_from_dict",
    "snapshot_to_json",
    "snapshot_from_json",
    "bars_to_csv",
    "bars_from_csv",
]
