"""Quote (bid/ask level 1) data model and converters.

Level 1 market data (best bid/ask) useful for spread analysis and order routing.
Represents the best bid and ask prices (and sometimes sizes) at a point in time.
"""

# pylint: disable=duplicate-code

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(..., description="Quote timestamp, tz-aware UTC")
    bid_price: float = Field(..., description="Best bid price")
    ask_price: float = Field(..., description="Best ask price")
    bid_size: float | None = Field(default=None, description="Bid size in shares")
    ask_size: float | None = Field(default=None, description="Ask size in shares")
    bid_exchange: str | None = Field(default=None, description="Bid exchange code")
    ask_exchange: str | None = Field(default=None, description="Ask exchange code")
    conditions: list[str] | None = Field(default=None, description="Quote conditions/modifiers")
