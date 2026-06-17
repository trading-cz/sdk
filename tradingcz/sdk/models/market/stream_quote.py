"""StreamQuote — a streaming quote from a broker.

Wraps a raw Quote with metadata from the broker's streaming feed.
Used by strategies consuming live market data.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.models.market.quote import Quote

# TODO: move to ingestion ??
class StreamQuote(BaseModel):
    """A streaming quote from a broker.

    Contains the raw Quote plus broker-level metadata.
    """

    model_config = ConfigDict(frozen=True)
    symbol: str
    timestamp: datetime
    quote: Quote
    broker: str = "alpaca"

__all__ = ["StreamQuote"]
