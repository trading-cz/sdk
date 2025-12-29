"""Bar (OHLCV candlestick) domain model."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Bar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime       # Opening time, tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None   # Number of trades in bar
    vwap: float | None = None        # Volume-weighted average price
