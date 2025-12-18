"""Kafka message key models for market data events.

These Pydantic models define the key structure for Kafka topics,
enabling proper message partitioning and routing.
"""

from pydantic import BaseModel, Field


class MarketStockQuoteKey(BaseModel):
    """Kafka key for stock quote messages.

    Partitions quote messages by symbol and maintains order per symbol.
    """
    symbol: str = Field(description="Ticker symbol (e.g., 'AAPL', 'SPY')")
    sequence: int = Field(description="Monotonically increasing sequence number for this symbol")


class MarketStockTradeKey(BaseModel):
    """Kafka key for stock trade messages.

    Partitions trade messages by symbol and maintains order per symbol.
    """
    symbol: str = Field(description="Ticker symbol (e.g., 'AAPL', 'SPY')")
    sequence: int = Field(description="Monotonically increasing sequence number for this symbol")


class RawSignalKey(BaseModel):
    """Kafka key for raw signal messages from strategies.

    Partitions signal messages by strategy and symbol for organized processing.
    """
    strategy_id: str = Field(description="Strategy identifier (e.g., 'momentum-01', 'mean-reversion')")
    symbol: str = Field(description="Ticker symbol (e.g., 'AAPL', 'SPY')")
