"""Module for Stop Order request model"""

from typing import Self

from pydantic import Field, model_validator

from tradingcz.sdk.models.enums.order import OrderClass
from tradingcz.sdk.models.orders.order import OrderRequest


class StopOrderRequest(OrderRequest):
    """Model for Stop Order request"""

    # Non-optional fields for stop order
    order_class: OrderClass | None = Field(default=OrderClass.SIMPLE)
    stop_price: float | None = Field(..., description="Stop price for buying or selling")

    @model_validator(mode="after")
    def check_qty_or_notional(self) -> Self:
        """Validate that either 'qty' or 'notional' is provided, but not both."""

        present = sum([self.qty is not None, self.notional is not None])
        if present != 1:
            raise ValueError("Exactly one of 'qty' or 'notional' must be provided")

        return self
