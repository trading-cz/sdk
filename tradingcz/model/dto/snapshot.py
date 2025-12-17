"""Market snapshot data transfer object."""

from dataclasses import dataclass
from typing import Optional, Any

from .bar import Bar
from .quote import Quote
from .trade import Trade


@dataclass(slots=True)
class Snapshot:
    """Complete market snapshot - current state for a symbol.
    
    Combines latest trade, quote, and bars into a single view.
    Useful for dashboards and real-time monitoring.
    
    Attributes:
        symbol: Ticker symbol (e.g., "AAPL")
        latest_trade: Most recent trade (optional)
        latest_quote: Most recent bid/ask quote (optional)
        minute_bar: Latest minute bar (optional)
        daily_bar: Latest daily bar (optional)
        raw: Provider's original object for debugging (optional)
    
    Example:
        snapshot = provider.get_snapshot(["AAPL"])["AAPL"]
        print(f"Last price: {snapshot.latest_trade.price}")
        print(f"Spread: {snapshot.latest_quote.ask_price - snapshot.latest_quote.bid_price}")
    """
    symbol: str
    latest_trade: Optional[Trade] = None
    latest_quote: Optional[Quote] = None
    minute_bar: Optional[Bar] = None
    daily_bar: Optional[Bar] = None
    raw: Optional[Any] = None
