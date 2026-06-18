"""Corporate action models — dividends and stock splits."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Dividend(BaseModel):
    """A single dividend payment event."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    ex_date: date = Field(..., description="Ex-dividend date")
    pay_date: date | None = Field(default=None, description="Payment date")
    amount: float = Field(..., description="Dividend amount per share")
    currency: str = Field(default="USD", description="Currency")
    timestamp: datetime | None = Field(default=None, description="Event timestamp")


class StockSplit(BaseModel):
    """A single stock split event."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    ex_date: date = Field(..., description="Ex-split date")
    old_rate: float = Field(..., description="Old shares (numerator)")
    new_rate: float = Field(..., description="New shares (denominator)")
    timestamp: datetime | None = Field(default=None, description="Event timestamp")


__all__ = ["Dividend", "StockSplit"]
