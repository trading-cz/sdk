"""Trade (tick) domain model.
Individual trade (tick) - for tick-level analysis.
Represents a single executed trade at a point in time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class Trade:  # pylint: disable=too-many-instance-attributes
    symbol: str
    timestamp: datetime       # tz-aware UTC
    price: float
    size: float
    exchange: str | None = None
    trade_id: str | None = None
    conditions: list[str] | None = None
