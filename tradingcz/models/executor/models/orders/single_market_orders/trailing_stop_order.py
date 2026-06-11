"""Module for Trailing Stop Order request model"""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from tradingcz.models.enums.order import OrderClass, OrderSide, TimeInForce


class TrailingStopOrderRequest(BaseModel):
    """Model for Trailing Stop Order request"""

    # Non-optional fields for trailing stop order
    symbol: str = Field(..., description="Ticker symbol", min_length=1)
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    side: OrderSide = Field(..., description="Order side, sell or buy")
    time_in_force: TimeInForce = Field(
        ..., description="Lifecycle of the order: day,  gtc, etc."
    )
    order_class: OrderClass | None = Field(default=OrderClass.SIMPLE)

    group_id: str | None = Field(default=None, index=True)

    # Trailing stop fields
    trail_price: float | None = Field(
        default=None,
        description="Trailing stop price, set with respect to high water mark since"
        "creation of the order at broker",
    )
    trail_percent: float | None = Field(
        default=None,
        description="Trailing stop percentage, set with respect to high water mark since"
        "creation of the order at broker",
    )

    @model_validator(mode="after")
    def check_qty_or_notional(self) -> Self:
        """Validate that either 'qty' or 'notional' is provided, but not both."""

        present = sum([self.qty is not None, self.notional is not None])
        if present != 1:
            raise ValueError("Exactly one of 'qty' or 'notional' must be provided")

        return self

    @model_validator(mode="after")
    def check_trailing_stop_fields(self) -> Self:
        """Validate that trailing stop fields are provided correctly"""

        if (self.trail_price is not None) and (self.trail_percent is not None):
            raise ValueError(
                "Only one of 'trail_price' or 'trail_percent' can be provided"
            )

        return self
