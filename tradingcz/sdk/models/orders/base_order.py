"""BaseOrderRequest — common base for all order request types."""

from pydantic import BaseModel, Field


class BaseOrderRequest(BaseModel):
    """Base class for all order request types.

    Guarantees that every order has a ``symbol`` field, which allows
    callers to access ``order.symbol`` directly without type narrowing
    or getattr workarounds.
    """

    symbol: str = Field(..., description="Ticker symbol", min_length=1)


__all__ = ["BaseOrderRequest"]
