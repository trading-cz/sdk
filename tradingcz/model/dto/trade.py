"""Trade (tick) data transfer object."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass(slots=True)
class Trade:
    """Individual trade (tick) - for tick-level analysis and volume profiling.
    
    Attributes:
        symbol: Ticker symbol (e.g., "AAPL")
        timestamp: Trade execution time, timezone-aware UTC
        price: Trade price
        size: Trade size (shares/contracts)
        exchange: Exchange where trade occurred (optional)
        trade_id: Unique trade identifier (optional)
        conditions: Trade condition codes (optional)
        raw: Provider's original object for debugging (optional)
    
    Example:
        trade = Trade(
            symbol="AAPL",
            timestamp=datetime.now(timezone.utc),
            price=150.25,
            size=100,
            exchange="XNAS",
        )
    """
    symbol: str
    timestamp: datetime
    price: float
    size: float
    exchange: Optional[str] = None
    trade_id: Optional[str] = None
    conditions: Optional[list[str]] = None
    raw: Optional[Any] = None
