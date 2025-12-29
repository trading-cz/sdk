"""Snapshot (aggregated market state) domain model.

Combines the latest trade, quote, minute bar, and daily bar in one call.
    More efficient than calling individual methods separately.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tradingcz.model.ingestion.bar import Bar
from tradingcz.model.ingestion.quote import Quote
from tradingcz.model.ingestion.trade import Trade


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    minute_bar: Bar | None = None
    daily_bar: Bar | None = None
    previous_daily_bar: Bar | None = None
