"""HTTP response model for Bar (OHLCV candlestick) data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict  # pylint: disable=import-error

from tradingcz.model.domain.bar import Bar


class BarResponse(BaseModel):
    """HTTP response model for a single bar.

    Validates JSON schema and provides Swagger documentation.
    Used by FastAPI to serialize Bar to JSON automatically.
    """
    timestamp: str          # ISO format
    open: float
    high: float
    low: float
    close: float
    volume: int
    trade_count: int | None = None
    vwap: float | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-01-15T09:30:00+00:00",
                "open": 150.0,
                "high": 152.5,
                "low": 149.8,
                "close": 151.2,
                "volume": 2500000,
                "trade_count": 45000,
                "vwap": 151.05
            }
        }
    )


def bar_to_response(bar: Bar) -> BarResponse:
    """Convert Bar domain model to HTTP response.

    Args:
        bar: Bar domain model

    Returns:
        BarResponse (Pydantic model) ready for JSON serialization
    """
    return BarResponse(
        timestamp=bar.timestamp.isoformat(),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=int(bar.volume),
        trade_count=bar.trade_count,
        vwap=bar.vwap,
    )
