"""Model for validating response from brokers when submitting an order.
This is used to update the database with the order id and status."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from tradingcz.models.enums.order import (
    OrderClass,
    OrderSide,
    OrderStatus,
    TimeInForce,
)


class BrokerOrderResponse(BaseModel):
    """Model for validating response from brokers when submitting an order.
    This is used to update the database with the order id and status."""

    model_config = ConfigDict(frozen=True, extra_ignore=True, use_enum_values=True)

    id: UUID = Field(..., validation_alias=AliasChoices("client_order_id"))
    broker_order_id: UUID | None = Field(
        validation_alias=AliasChoices("id"), default=None
    )

    # Basic order fields
    order_status: OrderStatus | None = Field(
        validation_alias=AliasChoices("status"), default=None
    )
    symbol: str
    qty: float | None
    notional: float | None
    side: OrderSide | None
    time_in_force: TimeInForce | None
    order_class: OrderClass | None
    limit_price: float | None
    stop_price: float | None

    filled_qty: float | None
    filled_avg_price: float | None

    # timestamp fields
    created_at: datetime | None
    updated_at: datetime | None
    submitted_at: datetime | None
    filled_at: datetime | None
    expired_at: datetime | None
    expires_at: datetime | None
    canceled_at: datetime | None
    failed_at: datetime | None

    # Trailing stop fields
    trail_percent: float | None
    trail_price: float | None
    hwm: float | None

    # raw_broker_response: dict | None
    raw_broker_response: dict[str, Any] = Field(default_factory=dict)  # by gemini

    @model_validator(mode="before")
    @classmethod
    def capture_raw_response(cls, data: Any) -> Any:
        """Capture the raw broker response in the model."""
        if isinstance(data, dict):
            data["raw_broker_response"] = data.copy()
        return data
