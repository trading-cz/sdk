"""Snapshot (aggregated market state) domain model.

Combines the latest trade, quote, minute bar, and daily bar in one call.
    More efficient than calling individual methods separately.
"""

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.models.market.bar import Bar
from tradingcz.sdk.models.market.quote import Quote
from tradingcz.sdk.models.market.trade import Trade


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    minute_bar: Bar | None = None
    daily_bar: Bar | None = None
    previous_daily_bar: Bar | None = None
