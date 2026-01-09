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
    STOP = "stop"               # Trigger market order at stop price (both sides)
    # STOP_LIMIT = "stop_limit"   # Trigger limit order at stop price (both sides)
    # TRAILING_STOP

class OrderClass(str, Enum):
    """Order class, e.g. simple or bracket order."""
    SIMPLE = "simple"       # Simple order, also ""
    BRACKET = "bracket"     # Bracket order with either take_profit or stop_loss or both
    OCO = "oco"             # OCO order
    OTO = "oto"             # OTO limit order
    MLEG = "mleg"           # For multi-leg options


class TimeInForce(str, Enum):
    """Time for which is order live"""
    GTC = "gtc" # Good until canceled
    DAY = "day" # Eligible for execution only until end of day
    IOC = "ioc" # Instant for any part of the order, the rest or the whole order is otherwise immediately cancelled
    FOK = "fok" # Fill or kill whole order only immediately
    CLS = "cls" # Market/limit on market close - only in market closing auction
    OPG = "opg" # Market/limit on market open - only in market opening auction

