"""Module for Limit Order request model"""

from typing import Self

from pydantic import Field, model_validator

from tradingcz.sdk.models.enums.order import OrderClass, TimeInForce
from tradingcz.sdk.models.orders.base_order import BaseOrderRequest


class LimitOrderRequest(BaseOrderRequest):
    """Model for Limit Order request"""

    # Non-optional fields for limit order
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    time_in_force: TimeInForce = Field(
        ..., description="Lifecycle of the order: day,  gtc, etc."
    )
    order_class: OrderClass | None = Field(default=OrderClass.SIMPLE)
    limit_price: float | None = Field(
        ..., description="Limit price for buying or selling"
    )

    @model_validator(mode="after")
    def check_qty_or_notional(self) -> Self:
        """Validate that either 'qty' or 'notional' is provided, but not both."""

        present = sum([self.qty is not None, self.notional is not None])
        if present != 1:
            raise ValueError("Exactly one of 'qty' or 'notional' must be provided")

        return self
