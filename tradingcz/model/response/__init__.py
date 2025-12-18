"""Response models for REST APIs and Kafka keys.

Contains Pydantic models for:
- HTTP responses (Bar, Quote, Trade, Snapshot)
- Kafka message keys (MarketStockQuoteKey, MarketStockTradeKey, RawSignalKey)
"""

from tradingcz.model.response.bar import BarResponse, bar_to_response
from tradingcz.model.response.quote import QuoteResponse, quote_to_response
from tradingcz.model.response.trade import TradeResponse, trade_to_response
from tradingcz.model.response.snapshot import SnapshotResponse, snapshot_to_response
from tradingcz.model.response.kafka_keys import (
    MarketStockQuoteKey,
    MarketStockTradeKey,
    RawSignalKey,
)

__all__ = [
    # HTTP Response Models
    "BarResponse",
    "QuoteResponse",
    "TradeResponse",
    "SnapshotResponse",
    # Response Converters
    "bar_to_response",
    "quote_to_response",
    "trade_to_response",
    "snapshot_to_response",
    # Kafka Key Models
    "MarketStockQuoteKey",
    "MarketStockTradeKey",
    "RawSignalKey",
]
