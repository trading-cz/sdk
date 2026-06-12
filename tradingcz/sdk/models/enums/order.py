from enum import StrEnum


class SortOrder(StrEnum):
    """Sort order for time-series data."""

    ASC = "asc"  # Oldest first (default for backtesting)
    DESC = "desc"  # Newest first (for latest-N queries)


class OrderSide(StrEnum):
    """Order side for trading."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Order execution type."""

    MARKET = "market"  # Execute at current market price
    LIMIT = "limit"  # Execute at specified price or better
    STOP = "stop"  # Trigger market order at stop price (both sides)
    # STOP_LIMIT = "stop_limit"   # Trigger limit order at stop price (both sides)
    # TRAILING_STOP


class OrderClass(StrEnum):
    """Order class, e.g. simple or bracket order."""

    SIMPLE = "simple"  # Simple order, also ""
    BRACKET = "bracket"  # Bracket order with either take_profit or stop_loss or both
    OCO = "oco"  # OCO order
    OTO = "oto"  # OTO limit order
    MLEG = "mleg"  # For multi-leg options


class TimeInForce(StrEnum):
    """Time for which is order live"""

    GTC = "gtc"  # Good until canceled
    DAY = "day"  # Eligible for execution only until end of day
    IOC = "ioc"  # Instant for any part of the order, the rest or the whole order is otherwise immediately cancelled
    FOK = "fok"  # Fill or kill whole order only immediately
    CLS = "cls"  # Market/limit on market close - only in market closing auction
    OPG = "opg"  # Market/limit on market open - only in market opening auction


class OrderStatus(StrEnum):
    """Order status."""

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    PENDING_NEW = "pending_new"
    ACCEPTED_FOR_BIDDING = "accepted_for_bidding"
    STOPPED = "stopped"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"
    HELD = "held"


TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }
)
