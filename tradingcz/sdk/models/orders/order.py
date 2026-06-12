"""Module for Market Order request model"""

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.order import OrderClass, OrderSide, TimeInForce


class OrderRequest(BaseModel):
    """Model for Market Order request"""

    # Non-optional fields for market order
    symbol: str = Field(..., description="Ticker symbol", min_length=1)
    qty: float | None = Field(default=None)
    notional: float | None = Field(default=None)
    side: OrderSide = Field(..., description="Order side, sell or buy")
    time_in_force: TimeInForce = Field(..., description="Lifecycle of the order: day,  gtc, etc.")
    order_class: OrderClass | None = Field(
        default=None, description="Order class, for possible values see enmum OrderClass"
    )

    group_id: str | None = Field(
        default=None, index=True, description="Not sure what's this for. In case?"
    )
