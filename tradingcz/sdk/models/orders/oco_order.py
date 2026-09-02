"""Module for OCO Order request model"""

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from tradingcz.sdk.models.enums.order import OrderClass, TimeInForce
from tradingcz.sdk.models.orders.base_order import BaseOrderRequest


class OcoOrderRequest(BaseOrderRequest):
    """Model for OCO Order request. One Cancels Other: create two legs of
    the same side order, take profit and stop loss leg. Both are mandatory.
    Take profit leg can be replaced with timed leg - order will be closed at given time,
    if stop loss leg is not triggered before."""

    # Basic fields for OCO order
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    time_in_force: TimeInForce = Field(
        ..., description="Lifecycle of the order: day,  gtc, etc."
    )
    order_class: OrderClass = Field(default=OrderClass.OCO)
    limit_price: float | None = Field(
        default=None, description="Limit price for buying or selling"
    )
    stop_price: float | None = Field(
        default=None, description="Stop price for buying or selling"
    )

    # Leg fields
    tp_limit_price: float | None = Field(
        default=None, description="Limit price for take profit order"
    )
    sl_stop_price: float = Field(
        ..., description="Stop price (trigger) for stop loss order"
    )
    sl_limit_price: float | None = Field(
        default=None, description="Limit price for stop loss order"
    )

    # Timed leg
    tp_limit_time: datetime | None = Field(
        default=None, description="Expiration time for take profit leg"
    )

    @model_validator(mode="after")
    def check_qty_or_notional(self) -> Self:
        """Validate that either 'qty' or 'notional' is provided, but not both."""

        present = sum([self.qty is not None, self.notional is not None])
        if present != 1:
            raise ValueError("Exactly one of 'qty' or 'notional' must be provided")

        return self

    @model_validator(mode="after")
    def check_tp_limit_or_time(self) -> Self:
        """Validate that either 'tp_limit_price' or 'tp_limit_time' is provided, but not both."""

        present = sum([self.tp_limit_price is not None, self.tp_limit_time is not None])
        if present != 1:
            raise ValueError(
                "Exactly one of 'tp_limit_price' or 'tp_limit_time' must be provided"
            )

        return self
