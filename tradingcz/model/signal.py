"""Trading signal model — strategy output.

Shared by all strategies so downstream consumers (risk, executor) receive
a consistent envelope regardless of which strategy produced a signal.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TradingSignal(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    strategy_id: str = Field(default="")
    open_price: float
    entry_price: float
    stop_loss: float
    valid_until_et: datetime
    atr_period: int = 3
    atr_value: float
