"""Bar (OHLCV candlestick) domain model."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Bar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(..., description="Opening time, tz-aware UTC")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="Highest price in period")
    low: float = Field(..., description="Lowest price in period")
    close: float = Field(..., description="Closing price")
    volume: float = Field(..., description="Total volume traded")
    trade_count: int | None = Field(default=None, description="Number of trades in bar")
    vwap: float | None = Field(default=None, description="Volume-weighted average price")
