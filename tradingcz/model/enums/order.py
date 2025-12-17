"""Order-related enumerations."""

from enum import Enum


class SortOrder(str, Enum):
    """Sort order for time-series data."""
    ASC = "asc"   # Oldest first (default for backtesting)
    DESC = "desc" # Newest first (for latest-N queries)


class OrderSide(str, Enum):
    """Order side for trading."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order execution type."""
    MARKET = "market"           # Execute at current market price
    LIMIT = "limit"             # Execute at specified price or better
    STOP = "stop"               # Trigger market order at stop price
    STOP_LIMIT = "stop_limit"   # Trigger limit order at stop price
