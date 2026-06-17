"""Module defining Prometheus metrics for the trading executor."""

from prometheus_client import Counter, Gauge, Histogram

EXECUTION_REQUESTS_RECEIVED = Counter(
    "execution_requests_received_total", "Execution requests received"
)
ORDERS_PLACED = Counter(
    "trading_orders_placed_total",
    "Total number of orders placed",
    ["side", "symbol"],  # labels = dimensions you can filter by
)

ORDER_LATENCY = Histogram(
    "trading_order_latency_seconds",
    "Time from order submission to confirmation",
    ["exchange"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

EXCHANGE_CONNECTED = Gauge(
    "trading_exchange_connected",
    "Whether exchange WebSocket is connected (1=yes, 0=no)",
    ["exchange"],
)

OPEN_POSITIONS = Gauge(
    "trading_open_positions_count", "Number of currently open positions"
)
