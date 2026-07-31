"""Module for Bracket Order request model"""

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from tradingcz.sdk.models.enums.order import OrderClass, OrderSide, TimeInForce
from tradingcz.sdk.models.orders.base_order import BaseOrderRequest


class BracketOrderRequest(BaseOrderRequest):
    """Model for Bracket Order request. Also called OTOCO: OTO where exit side is OCO"""

    # Basic fields for entry side - limit is optional
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    side: OrderSide = Field(..., description="Order side, sell or buy")
    time_in_force: TimeInForce = Field(
        ..., description="Lifecycle of the order: day,  gtc, etc."
    )
    order_class: OrderClass | None = Field(default=OrderClass.BRACKET)
    limit_price: float | None = Field(
        default=None, description="Limit price for buying or selling"
    )
    stop_price: float | None = Field(
        default=None, description="Stop price for buying or selling"
    )

    # Leg fields for exit side
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
        """Validate that both legs for exit side are provided."""

        present_tp = (
            1
            if (self.tp_limit_price is not None or self.tp_limit_time is not None)
            else 0
        )
        present_sl = (
            1
            if (self.sl_stop_price is not None or self.sl_limit_time is not None)
            else 0
        )
        if present_tp != 1 or present_sl != 1:
            raise ValueError(
                "Bracket order requires 'tp_limit_price' or 'tp_limit_time' to be provided, "
                "and 'sl_stop_price' or 'sl_limit_time' to be provided"
            )

        return self
