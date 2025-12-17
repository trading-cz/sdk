"""Quote (bid/ask) data transfer object."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass(slots=True)
class Quote:
    """Level 1 bid/ask quote - for spread analysis and order routing.
    
    Attributes:
        symbol: Ticker symbol (e.g., "AAPL")
        timestamp: Quote time, timezone-aware UTC
        bid_price: Best bid price
        ask_price: Best ask price
        bid_size: Size available at bid (optional)
        ask_size: Size available at ask (optional)
        bid_exchange: Exchange code for bid (optional)
        ask_exchange: Exchange code for ask (optional)
        conditions: Quote condition codes (optional)
        raw: Provider's original object for debugging (optional)
    
    Example:
        quote = Quote(
            symbol="AAPL",
            timestamp=datetime.now(timezone.utc),
            bid_price=150.25,
            ask_price=150.30,
            bid_size=100,
            ask_size=200,
        )
        spread = quote.ask_price - quote.bid_price  # 0.05
    """
    symbol: str
    timestamp: datetime
    bid_price: float
    ask_price: float
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    bid_exchange: Optional[str] = None
    ask_exchange: Optional[str] = None
    conditions: Optional[list[str]] = None
    raw: Optional[Any] = None
