"""General Order event model, used for both order creation and order update events."""

from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradingcz.model.enum.order import OrderClass, OrderSide, OrderStatus, TimeInForce

# will not use sdk in dev
# from tradingcz.model.enum.order import OrderClass, OrderSide, TimeInForce


# TODO Fields number and format is not final
# TODO na poradi orderu nezalezi


class SingleOrderRequest(BaseModel):
    """Basic recipe for single omarket order request model, with static field values, frozen,
    because it represents market order request event received via generic listener"""

    model_config = ConfigDict(frozen=True, use_enum_values=True)

    # Internl event/order id
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the order")
    order_status: OrderStatus | None = Field(default=None, description="Order status")
    timestamp_placeholder: datetime | None = Field(
        default=None,
        description="Timestamp for something TBD",  # TODO
    )
    # Basic order fields for simple orders
    symbol: str = Field(..., description="Ticker symbol", min_length=1)
    qty: float | None = Field(
        default=None, description="Quantity of the order, used as an alternative to notional"
    )
    notional: float | None = Field(
        default=None, description="Total value of the order, used as an alternative to qty"
    )
    side: OrderSide = Field(..., description="Order side, sell or buy")
    time_in_force: TimeInForce = Field(..., description="Lifecycle of the order: day,  gtc, etc.")
    order_class: OrderClass | None = Field(
        default=None, description="Order class, simple, oco, oto, etc."
    )
    limit_price: float | None = Field(default=None, description="Limit price for buying or selling")

    # Leg fields for advanced order types (oco, oto, bracket orders)
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

    # Trailing stop fields
    trail_price: float | None = Field(
        default=None, description="Trailing stop price for trailing stop orders"
    )
    trail_percent: float | None = Field(
        default=None, description="Trailing stop percentage for trailing stop orders"
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
            raise ValueError("Only one of 'trail_price' or 'trail_percent' can be provided")

        return self
