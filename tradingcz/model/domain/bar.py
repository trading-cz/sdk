"""Bar (OHLCV candlestick) domain model."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class Bar:
    symbol: str
    timestamp: datetime       # Opening time, tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None   # Number of trades in bar
    vwap: float | None = None        # Volume-weighted average price
