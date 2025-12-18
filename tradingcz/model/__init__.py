"""Trading Model - Shared data models for the trading platform.

This package provides:
- Enums: Timeframe, Adjustment, SortOrder, OrderSide, OrderType
- Domain Models: Bar, Quote, Trade, Snapshot (pure dataclasses)
- Response Models: HTTP responses and Kafka keys

Usage:
    from tradingcz.model import Timeframe, Bar, Quote
    from tradingcz.model.response import BarResponse, QuoteResponse
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
]
