"""Quote (bid/ask level 1) data model and converters.

Level 1 market data (best bid/ask) useful for spread analysis and order routing.
Represents the best bid and ask prices (and sometimes sizes) at a point in time.
"""
# pylint: disable=duplicate-code
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime       # tz-aware UTC
    bid_price: float
    ask_price: float
    bid_size: float | None = None
    ask_size: float | None = None
    bid_exchange: str | None = None
    ask_exchange: str | None = None
    conditions: list[str] | None = None
