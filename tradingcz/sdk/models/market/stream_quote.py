"""StreamQuote — a streaming quote from a broker.

Wraps a raw Quote with metadata from the broker's streaming feed.
Used by strategies consuming live market data.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import Broker
from tradingcz.sdk.models.market.quote import Quote

# TODO: move to ingestion ??
class StreamQuote(BaseModel):
    """A streaming quote from a broker.

    Contains the raw Quote plus broker-level metadata.
    """

    model_config = ConfigDict(frozen=True)
    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(..., description="Stream timestamp, tz-aware UTC")
    quote: Quote = Field(..., description="Market quote data")
    broker: str = Field(default=Broker.ALPACA, description="Broker providing the stream")

__all__ = ["StreamQuote"]
