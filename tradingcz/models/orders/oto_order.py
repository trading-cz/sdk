"""Module for OTO Order request model"""

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from tradingcz.models.enums.order import OrderClass
from tradingcz.models.orders.order import OrderRequest


class OtoOrderRequest(OrderRequest):
    """Model for OTO Order request. One triggers Other: Create market/limit order for entry side
    and a leg for exit."""

    # Basic fields for entry side - limit is optional
    order_class: OrderClass | None = Field(default=OrderClass.OTO)
    limit_price: float | None = Field(default=None, description="Limit price for buying or selling")
    stop_price: float | None = Field(default=None, description="Stop price for buying or selling")

    # Leg fields for exit side - PICK ONE
    tp_limit_price: float | None = Field(
        default=None, description="Limit price for take profit order"
    )
    sl_stop_price: float | None = Field(
        default=None, description="Stop price (trigger) for stop loss order"
    )
    sl_limit_price: float | None = Field(
        default=None, description="Limit price for stop loss order"
    )

    # Timed legs
    tp_limit_time: datetime | None = Field(
        default=None, description="Expiration time for take profit limit order"
    )
    sl_limit_time: datetime | None = Field(
        default=None, description="Expiration time for stop loss limit order"
    )

    @model_validator(mode="after")
    def check_qty_or_notional(self) -> Self:
        """Validate that either 'qty' or 'notional' is provided, but not both."""

        present = sum([self.qty is not None, self.notional is not None])
        if present != 1:
            raise ValueError("Exactly one of 'qty' or 'notional' must be provided")

        return self

    @model_validator(mode="after")
    def check_tp_or_sl(self) -> Self:
        """Validate that either 'take profit' or 'stop_loss' is provided, but not both."""

        # TODO to be refined - validate legs and prices vs times
        present_tp = sum([self.tp_limit_price is not None, self.tp_limit_time is not None])
        present_sl = sum([self.sl_stop_price is not None, self.sl_limit_time is not None])
        if present_tp + present_sl != 1:
            raise ValueError("OTO order requires either stop loss or take profit leg, but not both")

        return self
