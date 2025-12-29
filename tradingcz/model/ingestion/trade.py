"""Trade (tick) domain model.
Individual trade (tick) - for tick-level analysis.
Represents a single executed trade at a point in time.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Trade(BaseModel):  # pylint: disable=too-many-instance-attributes
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime       # tz-aware UTC
    price: float
    size: float
    exchange: str | None = None
    trade_id: str | None = None
    conditions: list[str] | None = None
