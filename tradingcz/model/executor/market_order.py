"""Simple market order with a possibility of OTO bracket order
"""
from pydantic import BaseModel, ConfigDict

from tradingcz.model.enum.order import OrderClass, OrderSide, OrderType, TimeInForce


class MarketOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    side: OrderSide
    time_in_force: TimeInForce
    # type: OrderType | None
    order_class: OrderClass | None
    stop_loss: dict[str, float] | None
