"""BaseOrderRequest — common base for all order request types."""

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.order import OrderSide


class BaseOrderRequest(BaseModel):
    """Base class for all order request types.

    Guarantees that every order has ``symbol`` and ``side``, which allows
    callers to access these fields directly without type narrowing or
    getattr workarounds.
    """

    symbol: str = Field(..., description="Ticker symbol", min_length=1)
    side: OrderSide = Field(..., description="Order side, sell or buy")


__all__ = ["BaseOrderRequest"]
