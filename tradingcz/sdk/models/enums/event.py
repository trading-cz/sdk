from enum import StrEnum

from tradingcz.sdk.models.orders.bracket_order import BracketOrderRequest
from tradingcz.sdk.models.orders.limit_order import LimitOrderRequest
from tradingcz.sdk.models.orders.market_order import MarketOrderRequest
from tradingcz.sdk.models.orders.oco_order import OcoOrderRequest
from tradingcz.sdk.models.orders.oto_order import OtoOrderRequest
from tradingcz.sdk.models.orders.stop_order import StopOrderRequest
from tradingcz.sdk.models.orders.trailing_stop_order import TrailingStopOrderRequest


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
    """Unified event type — used for both Kafka ``message_type`` headers
    and ``event_type`` payload fields.

    Canonical values driving deserialization routing and event dispatch.

    Usage::

        # Kafka wire header
        make_headers(message_type=EventType.DATA_REQUEST, ...)
        model = parse_message(EventType.DATA_READY, payload)

        # Event payload
        event = ExecutionRequestEvent(event_type=EventType.TRADING_SIGNAL, ...)
    """

    # ── Control-plane (event topic) ──────────────────────────────────────
    DATA_REQUEST = "data_request"
    DATA_READY = "data_ready"
    DATA_ERROR = "data_error"
    SERVICE_REQUEST = "service_request"
    SERVICE_LIFECYCLE = "service_lifecycle"

    # ── Service responses (event topic) ──────────────────────────────────
    POSITION_RESPONSE = "position_response"
    BALANCE_RESPONSE = "balance_response"
    ORDER_RESPONSE = "order_response"

    # ── Event payload types ──────────────────────────────────────────────
    EXECUTION_REQUEST = "execution_request"
    TRADING_SIGNAL = "trading_signal"

    # ── Market data (data topics) ────────────────────────────────────────
    BAR = "bar"
    QUOTE = "quote"
    TRADE = "trade"
    STREAM_QUOTE = "stream_quote"
    SNAPSHOT = "snapshot"
    OPTION_SNAPSHOT = "option_snapshot"


class StrategyType(StrEnum):
    """Strategy type."""

    INTRADAY_VOLATILITY_BREAKOUT = "intraday_volatility_breakout"
    SINGLE_ORDER = "single_order"


class ServiceRequestType(StrEnum):
    """Service request type."""

    REQUEST_CURRENT_POSITIONS = "request_current_positions"
    REQUEST_ORDERS_FOR_EVENT = "request_orders_for_event"
    REQUEST_CASH_BALANCE = "request_cash_balance"


type OrderRequest = (
    BracketOrderRequest
    | LimitOrderRequest
    | MarketOrderRequest
    | OcoOrderRequest
    | OtoOrderRequest
    | StopOrderRequest
    | TrailingStopOrderRequest
)
