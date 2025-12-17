"""OHLCV Bar data transfer object."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass(slots=True)
class Bar:
    """OHLCV bar (candlestick) - the core unit for backtesting and charting.
    
    Attributes:
        symbol: Ticker symbol (e.g., "AAPL", "MSFT")
        timestamp: Bar opening time, timezone-aware UTC
        open: Opening price
        high: Highest price during the bar
        low: Lowest price during the bar
        close: Closing price
        volume: Total volume traded
        trade_count: Number of trades in bar (optional)
        vwap: Volume-weighted average price (optional)
        raw: Provider's original object for debugging (optional)
    
    Example:
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime.now(timezone.utc),
            open=150.0, high=152.5, low=149.5, close=151.0,
            volume=1_000_000,
            vwap=150.75,
        )
    """
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: Optional[int] = None
    vwap: Optional[float] = None
    raw: Optional[Any] = None
