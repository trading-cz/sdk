"""Trading signal model — strategy output.

Shared by all strategies so downstream consumers (risk, executor) receive
a consistent envelope regardless of which strategy produced a signal.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TradingSignal(BaseModel):
    """Strategy output — direction + levels, intentionally without position size.

    Designed to be close to the executor's ExecutionRequestEvent so that a risk
    application can translate it by simply adding ``qty`` and ``order_class``.
    """

    symbol: str
    side: Literal["LONG", "SHORT"]
    strategy_id: str = Field(default="")
    open_price: float
    entry_price: float
    stop_loss: float
    valid_until_et: datetime
    atr_period: int = 3
    atr_value: float


__all__ = ["TradingSignal"]
