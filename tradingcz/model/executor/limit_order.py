"""Limit market order with a possibility of OCO bracket order
"""
from pydantic import BaseModel, ConfigDict


class LimitOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    side: str
    time_in_force: str
    limit_price: float
    type: str | None
    order_class: str | None
    stop_loss: dict[str, float] | None
    take_profit: dict[str, float] | None

