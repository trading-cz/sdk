"""HTTP response model for Quote (bid/ask level 1) data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tradingcz.model.domain.quote import Quote


class QuoteResponse(BaseModel):
    """HTTP response model for a single quote."""
    timestamp: str              # ISO format
    bid_price: float
    ask_price: float
    bid_size: float | None = None
    ask_size: float | None = None
    spread: float | None = None  # Calculated bid-ask spread

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-01-15T09:30:00+00:00",
                "bid_price": 150.50,
                "ask_price": 150.51,
                "bid_size": 1000,
                "ask_size": 1200,
                "spread": 0.01
            }
        }
    )


def quote_to_response(quote: Quote) -> QuoteResponse:
    """Convert Quote domain model to HTTP response.

    Args:
        quote: Quote domain model

    Returns:
        QuoteResponse (Pydantic model) ready for JSON serialization
    """
    spread = round(quote.ask_price - quote.bid_price, 4)
    return QuoteResponse(
        timestamp=quote.timestamp.isoformat(),
        bid_price=quote.bid_price,
        ask_price=quote.ask_price,
        bid_size=quote.bid_size,
        ask_size=quote.ask_size,
        spread=spread if quote.ask_price and quote.bid_price else None,
    )
