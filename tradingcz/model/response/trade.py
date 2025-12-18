"""HTTP response model for Trade (tick) data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict  # pylint: disable=import-error

from tradingcz.model.domain.trade import Trade


class TradeResponse(BaseModel):
    """HTTP response model for a single trade."""
    timestamp: str
    price: float
    size: float
    exchange: str | None = None
    trade_id: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-01-15T09:30:00+00:00",
                "price": 150.50,
                "size": 1000,
                "exchange": "XNAS",
                "trade_id": "1234567890"
            }
        }
    )


def trade_to_response(trade: Trade) -> TradeResponse:
    """Convert Trade domain model to HTTP response.

    Args:
        trade: Trade domain model

    Returns:
        TradeResponse (Pydantic model) ready for JSON serialization
    """
    return TradeResponse(
        timestamp=trade.timestamp.isoformat(),
        price=trade.price,
        size=trade.size,
        exchange=trade.exchange,
        trade_id=trade.trade_id,
    )
