from enum import StrEnum


class EventStatus(StrEnum):
    """Status of the event processing."""

    ACTIVE = "active"
    CLOSING = "closing"
    COMPLETED = "completed"
    EXECUTING = "executing"
    FAILED = "failed"
    IN_MARKET = "in_market"
    PROCESSING = "processing"
    RECEIVED = "received"
    REQUIRES_ATTENTION = "requires_attention"
    WAITING_FOR_TRIGGER = "waiting_for_trigger"


class EventType(StrEnum):
    """Event type for trading executor SDK."""

    EXECUTION_REQUEST = "execution_request"
    SERVICE_REQUEST = "service_request"


class StrategyType(StrEnum):
    """Strategy type."""

    INTRADAY_VOLATILITY_BREAKOUT = "intraday_volatility_breakout"
    SINGLE_ORDER = "single_order"


class ServiceRequestType(StrEnum):
    """Service request type."""

    REQUEST_CURRENT_POSITIONS = "request_current_positions"
    REQUEST_ORDERS_FOR_EVENT = "request_orders_for_event"
    REQUEST_CASH_BALANCE = "request_cash_balance"
