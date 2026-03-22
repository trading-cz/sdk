"""Module for Market Order request model"""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from tradingcz.executor.sdk.enum.enums import OrderClass, OrderSide, TimeInForce


class MarketOrderRequest(BaseModel):
    """Model for Market Order request"""

    # Non-optional fields for market order
    symbol: str = Field(..., description="Ticker symbol", min_length=1)
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    side: OrderSide = Field(..., description="Order side, sell or buy")
    time_in_force: TimeInForce = Field(..., description="Lifecycle of the order: day,  gtc, etc.")
    order_class: OrderClass | None = Field(default=OrderClass.SIMPLE)

    group_id: str | None = Field(default=None, index=True)

    @model_validator(mode="after")
    def check_qty_or_notional(self) -> Self:
        """Validate that either 'qty' or 'notional' is provided, but not both."""

        present = sum([self.qty is not None, self.notional is not None])
        if present != 1:
            raise ValueError("Exactly one of 'qty' or 'notional' must be provided")

        return self
