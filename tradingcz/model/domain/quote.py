"""Quote (bid/ask level 1) data model and converters.

Level 1 market data (best bid/ask) useful for spread analysis and order routing.
Represents the best bid and ask prices (and sometimes sizes) at a point in time.
"""
# pylint: disable=duplicate-code
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class Quote:
    symbol: str
    timestamp: datetime       # tz-aware UTC
    bid_price: float
    ask_price: float
    bid_size: float | None = None
    ask_size: float | None = None
    bid_exchange: str | None = None
    ask_exchange: str | None = None
    conditions: list[str] | None = None
