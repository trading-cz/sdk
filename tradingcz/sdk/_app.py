"""TradingApp — batteries-included SDK entry point.

Configuration is driven by environment variables (see ``KafkaSettings``).
Minimal setup — just provide a ``service_id``::

    from tradingcz.sdk import TradingApp

    app = TradingApp(service_id="my-strategy")
    await app.start()
    bars = await app.data.request_historical(["AAPL"])
    await app.close()

    # Or use the async context manager:
    async with TradingApp(service_id="my-strategy") as app:
        bars = await app.data.request_historical(["AAPL"])

Feature flags::

    app = TradingApp(service_id="risk-checker")
    app.with_signals(False).with_data(False)
    await app.start()
    # Only app.positions, app.balance, app.orders available

Environment variables::

    KAFKA_BOOTSTRAP_SERVERS  — Kafka broker addresses (default: localhost:9092)
    KAFKA_CONSUMER_GROUP     — Consumer group id (default: <service_id>)
    SDK_ENV                  — Environment name (default: dev)
    SDK_BROKER               — Broker identifier (default: alpaca)
"""

from __future__ import annotations

import os

from tradingcz.config.settings import KafkaSettings
from tradingcz.sdk._helpers import _FireAndForget, _RequestReply
from tradingcz.sdk.data import DataClient
from tradingcz.sdk.signals import SignalPublisher
from tradingcz.sdk.positions import PositionClient
from tradingcz.sdk.balance import BalanceClient
from tradingcz.sdk.orders import OrderClient
from tradingcz.transport.kafka.channel import KafkaChannel, KafkaTransport
from tradingcz.transport.kafka.topics import TopicRegistry


class TradingApp:
    """Batteries-included trading application.

    All client features are enabled by default.  Use ``.with_*(False)``
    to disable features you don't need.

    Configuration via environment variables (all optional):
        ``KAFKA_BOOTSTRAP_SERVERS``, ``KAFKA_CONSUMER_GROUP``,
        ``SDK_ENV``, ``SDK_BROKER``.

    Usage::

        async with TradingApp(service_id="my-strategy") as app:
            bars = await app.data.request_historical(["AAPL"])
            await app.signals.publish(signal)
    """

    def __init__(
        self,
        *,
        service_id: str,
        env: str | None = None,
        bootstrap_servers: str | None = None,
        broker: str | None = None,
    ) -> None:
        self._service_id = service_id
        self._env = env or os.environ.get("SDK_ENV", "dev")
        self._broker = broker or os.environ.get("SDK_BROKER", "alpaca")

        # Kafka settings — env vars take priority, else use reasonable defaults
        self._kafka = KafkaSettings(
            bootstrap_servers=bootstrap_servers
            or os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            consumer_group=os.environ.get("KAFKA_CONSUMER_GROUP", service_id),
        )

        self._enable_data = True
        self._enable_signals = True
        self._enable_positions = True
        self._enable_balance = True
        self._enable_orders = True

        # Set after start()
        self._transport: KafkaTransport | None = None
        self._topics: TopicRegistry | None = None
        self._events_channel: KafkaChannel | None = None
        self._rr: _RequestReply | None = None
        self._faf: _FireAndForget | None = None

        self.data: DataClient | None = None
        self.signals: SignalPublisher | None = None
        self.positions: PositionClient | None = None
        self.balance: BalanceClient | None = None
        self.orders: OrderClient | None = None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def with_data(self, enable: bool = True) -> "TradingApp":
        self._enable_data = enable
        return self

    def with_signals(self, enable: bool = True) -> "TradingApp":
        self._enable_signals = enable
        return self

    def with_positions(self, enable: bool = True) -> "TradingApp":
        self._enable_positions = enable
        return self

    def with_balance(self, enable: bool = True) -> "TradingApp":
        self._enable_balance = enable
        return self

    def with_orders(self, enable: bool = True) -> "TradingApp":
        self._enable_orders = enable
        return self

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize transport and enabled clients.

        Connects to Kafka, sets up channels, and starts background
        listeners for request/reply correlation.
        """
        self._transport = KafkaTransport(self._kafka)
        self._topics = TopicRegistry(env=self._env)
        self._events_channel = await self._transport.channel(self._topics.events.name)

        # Shared internal helpers
        self._rr = _RequestReply(self._events_channel, self._service_id)
        self._faf = _FireAndForget(self._events_channel, self._service_id)
        await self._rr.start()

        # Data client
        if self._enable_data:
            assert self._transport is not None
            assert self._topics is not None
            assert self._rr is not None
            self.data = DataClient(
                rr=self._rr,
                transport=self._transport,
                topics=self._topics,
                service_id=self._service_id,
                broker=self._broker,
            )

        # Signal publisher
        if self._enable_signals:
            assert self._faf is not None
            self.signals = SignalPublisher(faf=self._faf)

        # Position client
        if self._enable_positions:
            assert self._rr is not None
            self.positions = PositionClient(rr=self._rr)

        # Balance client
        if self._enable_balance:
            assert self._rr is not None
            self.balance = BalanceClient(rr=self._rr)

        # Order client
        if self._enable_orders:
            assert self._rr is not None
            self.orders = OrderClient(rr=self._rr)

    async def close(self) -> None:
        """Graceful shutdown — flushes queued messages and closes connections."""
        if self._rr is not None:
            await self._rr.close()
        if self._transport is not None:
            await self._transport.close()

    async def __aenter__(self) -> "TradingApp":
        """Async context manager entry — calls ``start()``."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit — calls ``close()``."""
        await self.close()
