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
    SERVICE_REQUEST = "service_request" # executor
    SERVICE_LIFECYCLE = "service_lifecycle"

    # ── Service responses (event topic) ──────────────────────────────────
    POSITION_RESPONSE = "position_response"
    BALANCE_RESPONSE = "balance_response"
    ORDER_RESPONSE = "order_response"

    # ── Event payload types ──────────────────────────────────────────────
    EXECUTION_REQUEST = "execution_request"
    TRADING_SIGNAL = "trading_signal"

    # ── Market data (data topics) ────────────────────────────────────────
    # TODO wrong enum - move somewhere else
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

class DataRequestType(StrEnum):
    """``DataRequest.type`` and ``DataReady.type`` — the kind of data-plane operation.

    Used on both sides of the request/reply pair:
    - ``DataRequest.type`` — what the client is asking for
    - ``DataReady.type``   — what the ingestion pod fulfilled

    ``UNSUBSCRIBE`` only appears in ``DataRequest``, never in ``DataReady``.
    """

    HISTORIC = "historic"
    STREAM = "stream"
    UNSUBSCRIBE = "unsubscribe"


class AssetType(StrEnum):
    """Asset class for a data request."""

    STOCK = "stock"
    OPTION = "option"
    CRYPTO = "crypto"


class MarketDataType(StrEnum):
    """``DataRequest.data_kind`` — kind of market-data records to fetch or stream.

    Used for both historical and streaming requests;
    ``DataRequest.type`` carries the historic/stream/unsubscribe
    distinction separately.

    Values:
        BARS            — OHLCV candlestick aggregates
        TRADES          — individual trade ticks
        QUOTES          — level-1 bid/ask quotes
        SNAPSHOTS       — combined trade + quote + greeks snapshot
        LATEST_BARS     — most-recent bar per symbol (no time range)
        LATEST_TRADES   — most-recent trade per symbol
        LATEST_QUOTES   — most-recent quote per symbol
    """

    BARS = "bars"
    TRADES = "trades"
    QUOTES = "quotes"
    SNAPSHOTS = "snapshots"
    LATEST_BARS = "latest_bars"
    LATEST_TRADES = "latest_trades"
    LATEST_QUOTES = "latest_quotes"
    DIVIDENDS = "dividends"
    SPLITS = "splits"


class Broker(StrEnum):
    """Supported market-data / execution brokers."""

    ALPACA = "alpaca"


class LifecycleEventType(StrEnum):
    """``LifecycleEvent.type`` — service health/lifecycle transitions."""

    INITIALIZING = "initializing"
    UP = "up"
    READY = "ready"
    HEARTBEAT = "heartbeat"
    DOWN = "down"