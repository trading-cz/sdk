"""Snapshot (aggregated market state) domain model.

Combines the latest trade, quote, minute bar, and daily bar in one call.
    More efficient than calling individual methods separately.
"""

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.market.bar import Bar
from tradingcz.sdk.models.market.quote import Quote
from tradingcz.sdk.models.market.trade import Trade
from tradingcz.sdk.registry import register_event


@register_event(EventType.SNAPSHOT)
class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    latest_trade: Trade | None = Field(default=None, description="Latest executed trade")
    latest_quote: Quote | None = Field(default=None, description="Latest bid/ask quote")
    minute_bar: Bar | None = Field(default=None, description="Latest one-minute bar")
    daily_bar: Bar | None = Field(default=None, description="Current day's bar")
    previous_daily_bar: Bar | None = Field(default=None, description="Previous day's bar")
