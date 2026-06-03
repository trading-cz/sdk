"""StreamQuote — a streaming quote from a broker.

Wraps a raw Quote with metadata from the broker's streaming feed.
Used by strategies consuming live market data.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from tradingcz.models.market.quote import Quote


class StreamQuote(BaseModel):
    """A streaming quote from a broker.

    Contains the raw Quote plus broker-level metadata.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    """Ticker symbol."""

    timestamp: datetime
    """Exchange timestamp (tz-aware UTC)."""

    quote: Quote
    """The underlying bid/ask quote."""

    broker: str = "alpaca"
    """Broker that provided this quote."""


__all__ = ["StreamQuote"]
