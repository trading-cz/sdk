from enum import StrEnum


class EventStatus(StrEnum):
    """Status of the event processing."""

    RECEIVED = "received"
    PROCESSING = "processing"
    EXECUTING = "executing"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(StrEnum):
    """Event type for trading executor SDK."""

    EXECUTION_REQUEST = "execution_request"
    SERVICE_REQUEST = "service_request"


class StrategyType(StrEnum):
    """Strategy type."""

    OCA_DUAL_BREAKOUT = "oca_dual_breakout"
    SINGLE_ORDER = "single_order"


class ServiceRequestType(StrEnum):
    """Service request type."""

    REQUEST_CURRENT_POSITIONS = "request_current_positions"
    REQUEST_CASH_BALANCE = "request_cash_balance"
