"""Snapshot (aggregated market state) domain model.

Combines the latest trade, quote, minute bar, and daily bar in one call.
    More efficient than calling individual methods separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from tradingcz.model.domain.bar import Bar
from tradingcz.model.domain.quote import Quote
from tradingcz.model.domain.trade import Trade


@dataclass(slots=True, frozen=True)
class Snapshot:
    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    minute_bar: Bar | None = None
    daily_bar: Bar | None = None
    previous_daily_bar: Bar | None = None
