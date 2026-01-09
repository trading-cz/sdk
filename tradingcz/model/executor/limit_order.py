"""Limit market order with a possibility of OCO bracket order
"""
from pydantic import BaseModel, ConfigDict

from tradingcz.model.enum.order import OrderClass, OrderSide, OrderType, TimeInForce


class LimitOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    side: OrderSide
    time_in_force: TimeInForce
    limit_price: float
    # type: OrderType | None
    order_class: OrderClass | None
    stop_loss: dict[str, float] | None
    take_profit: dict[str, float] | None
