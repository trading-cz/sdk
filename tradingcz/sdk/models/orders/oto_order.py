"""Module for OTO Order request model"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from tradingcz.sdk.models.enums.order import OrderClass, OrderSide, TimeInForce


class OtoOrderRequest(BaseModel):
    """Model for OTO Order request. One triggers Other: Create market/limit order for entry side
    and a leg for exit."""

    # Basic fields for entry side - limit is optional
    symbol: str = Field(..., description="Ticker symbol", min_length=1)
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    side: OrderSide = Field(..., description="Order side, sell or buy")
    time_in_force: TimeInForce = Field(
        ..., description="Lifecycle of the order: day,  gtc, etc."
    )
    order_class: OrderClass | None = Field(default=OrderClass.OTO)
    limit_price: float | None = Field(
        default=None, description="Limit price for buying or selling"
    )
    stop_price: float | None = Field(
        default=None, description="Stop price for buying or selling"
    )

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

        # Each leg is "present" if ANY of its fields are set
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
        if present_tp + present_sl != 1:
            raise ValueError(
                "OTO order requires either stop loss or take profit leg, but not both"
            )

        return self
