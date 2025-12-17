"""Trading Model - Shared data models for the trading platform.

This package provides:
- Enums: Timeframe, Adjustment, SortOrder, OrderSide, OrderType
- DTOs: Bar, Quote, Trade, Snapshot (for REST APIs and internal use)
- Kafka schemas: Generated from Avro (in generated/ folder)
- Converters: DTO ↔ Kafka schema utilities

Usage:
    from tradingcz.model import Timeframe, Bar, Quote
    from tradingcz.model.kafka.market_stock_quote import MarketStockQuoteValue
"""

from .enums import (
    Timeframe,
    Adjustment,
    SortOrder,
    OrderSide,
    OrderType,
)
from .dto import (
    Bar,
    Quote,
    Trade,
    Snapshot,
)

__all__ = [
    # Enums
    "Timeframe",
    "Adjustment",
    "SortOrder",
    "OrderSide",
    "OrderType",
    # DTOs
    "Bar",
    "Quote",
    "Trade",
    "Snapshot",
]
