"""TradingApp — batteries-included SDK entry point for strategies/consumers.

Configuration is driven by environment variables (see ``ServiceApp``).
Minimal setup — just provide a ``service_id``::

    from tradingcz.sdk.framework.trading import TradingApp

    async with TradingApp(service_id="my-strategy") as app:
        # One-time historical data
        bars = await app.stock.bars(["AAPL", "MSFT"], days=30)

        # Streaming data (context manager = guaranteed unsubscribe)
        async with app.stock.stream_quotes(["AAPL"]) as stream:
            async for quote in stream:
                if quote.quote.bid_price > threshold:
                    break

        # Publish a trading signal
        await app.signals.publish(signal)

Feature flags::

    app = TradingApp(service_id="risk-checker")
    app.with_signals(False).with_stock(False).with_options(False)

Multi-broker::

    async with TradingApp(service_id="arbitrage") as app:
        alpaca_bars = await app.stock.bars(["AAPL"])
        ibkr_chain = await app.with_broker("ibkr").options.chain("AAPL")

Environment variables::

    KAFKA_BOOTSTRAP_SERVERS  — Kafka broker addresses (default: localhost:9092)
    KAFKA_CONSUMER_GROUP     — Consumer group id (default: <service_id>)
    SDK_ENV                  — Environment name (default: dev)
    SDK_BROKER               — Broker identifier (default: alpaca)
    SDK_HEALTH_INTERVAL      — Heartbeat interval in seconds (default: 300)
"""

from __future__ import annotations

import os

from tradingcz.sdk.clients.balance import BalanceClient
from tradingcz.sdk.clients.base import BaseDataClient
from tradingcz.sdk.clients.data.corporate import CorporateActionsClient
from tradingcz.sdk.clients.data.options import OptionsDataClient
from tradingcz.sdk.clients.data.stock import StockDataClient
from tradingcz.sdk.clients.orders import OrderClient
from tradingcz.sdk.clients.positions import PositionClient
from tradingcz.sdk.clients.signals import SignalPublisher
from tradingcz.sdk.framework.helpers import FireAndForget, RequestReply
from tradingcz.sdk.framework.service import ServiceApp


class _BrokerScope:
    """Lightweight broker-scoped client factory.

    Returned by ``TradingApp.with_broker("ibkr")``.  Creates data
    clients that talk to the specified broker instead of the default.
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    @property
    def stock(self) -> StockDataClient:
        """Stock data client scoped to this broker."""
        return StockDataClient(self._base)

    @property
    def options(self) -> OptionsDataClient:
        """Options data client scoped to this broker."""
        return OptionsDataClient(self._base)

    @property
    def corporate_actions(self) -> CorporateActionsClient:
        """Corporate actions client scoped to this broker."""
        return CorporateActionsClient(self._base)


class TradingApp(ServiceApp):  # pylint: disable=too-many-instance-attributes
    """Batteries-included trading application for strategy/consumer role.

    Extends ``ServiceApp`` with client APIs:

    ========================= ============================================
    Attribute                 Client Class
    ========================= ============================================
    ``app.stock``             :class:`StockDataClient` — bars, quotes, trades
    ``app.options``           :class:`OptionsDataClient` — snapshots, chain
    ``app.corporate_actions`` :class:`CorporateActionsClient` — dividends, splits
    ``app.signals``           :class:`SignalPublisher` — publish trading signals
    ``app.positions``         :class:`PositionClient` — query positions
    ``app.balance``           :class:`BalanceClient` — query account balance
    ``app.orders``            :class:`OrderClient` — query orders
    ========================= ============================================

    All features enabled by default — use ``.with_*(False)`` to disable.

    **One-time vs. streaming**: Methods that return a plain ``dict``
    (``bars()``, ``snapshots()``, ``chain()``) are one-shot requests.
    Methods that return a :class:`StreamHandle` (``stream_quotes()``,
    ``stream_trades()``) yield data indefinitely — use ``async with`` for
    guaranteed unsubscribe on exit.

    Usage::

        async with TradingApp(service_id="my-strategy") as app:
            bars = await app.stock.bars(["AAPL"], days=30)

            async with app.stock.stream_quotes(["AAPL"]) as stream:
                async for quote in stream:
                    ...
    """

    def __init__(
        self,
        *,
        service_id: str,
        env: str | None = None,
        bootstrap_servers: str | None = None,
        broker: str | None = None,
        health_interval: float = 300.0,
    ) -> None:
        super().__init__(
            service_id=service_id,
            env=env,
            bootstrap_servers=bootstrap_servers,
            health_interval=health_interval,
        )
        self._broker = broker or os.environ.get("SDK_BROKER", "alpaca")

        self._enable_stock = True
        self._enable_options = True
        self._enable_corporate = True
        self._enable_signals = True
        self._enable_positions = True
        self._enable_balance = True
        self._enable_orders = True

        # Set after start()
        self._rr: RequestReply | None = None
        self._faf: FireAndForget | None = None
        self._base: BaseDataClient | None = None

        # Data clients
        self.stock: StockDataClient | None = None
        self.options: OptionsDataClient | None = None
        self.corporate_actions: CorporateActionsClient | None = None

        # Other clients
        self.signals: SignalPublisher | None = None
        self.positions: PositionClient | None = None
        self.balance: BalanceClient | None = None
        self.orders: OrderClient | None = None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def with_stock(self, enable: bool = True) -> TradingApp:
        """Enable/disable the stock data client (bars, quotes, trades)."""
        self._enable_stock = enable
        return self

    def with_options(self, enable: bool = True) -> TradingApp:
        """Enable/disable the options data client (snapshots, chain)."""
        self._enable_options = enable
        return self

    def with_corporate_actions(self, enable: bool = True) -> TradingApp:
        """Enable/disable the corporate actions client (dividends, splits)."""
        self._enable_corporate = enable
        return self

    def with_signals(self, enable: bool = True) -> TradingApp:
        self._enable_signals = enable
        return self

    def with_positions(self, enable: bool = True) -> TradingApp:
        self._enable_positions = enable
        return self

    def with_balance(self, enable: bool = True) -> TradingApp:
        self._enable_balance = enable
        return self

    def with_orders(self, enable: bool = True) -> TradingApp:
        self._enable_orders = enable
        return self

    # ------------------------------------------------------------------
    # Multi-broker support
    # ------------------------------------------------------------------

    def with_broker(self, broker: str) -> _BrokerScope:
        """Return a broker-scoped client factory.

        Creates data clients that talk to *broker* instead of the
        default broker configured at init time.  Useful for multi-broker
        strategies::

            async with TradingApp(service_id="arbitrage") as app:
                alpaca_bars = await app.stock.bars(["AAPL"])
                ibkr_chain = await app.with_broker("ibkr").options.chain("AAPL")

        Each ``with_broker()`` call creates a fresh ``BaseDataClient``
        so deduplication and transport state are isolated per broker.
        """
        assert self._rr is not None
        assert self.transport is not None
        assert self.topics is not None
        base = BaseDataClient(
            rr=self._rr,
            transport=self.transport,
            topics=self.topics,
            service_id=self.service_id,
            broker=broker,
        )
        return _BrokerScope(base)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize transport + client APIs."""
        await super().start()

        assert self.events_channel is not None
        assert self.transport is not None
        assert self.topics is not None

        # Shared internal helpers — use source_app for consistent header identity
        self._rr = RequestReply(self.events_channel, self.source_app)
        self._faf = FireAndForget(self.events_channel, self.source_app)
        await self._rr.start()

        # Shared base for all data clients (default broker)
        self._base = BaseDataClient(
            rr=self._rr,
            transport=self.transport,
            topics=self.topics,
            service_id=self.service_id,
            broker=self._broker,
        )

        # Stock data client
        if self._enable_stock:
            self.stock = StockDataClient(self._base)

        # Options data client
        if self._enable_options:
            self.options = OptionsDataClient(self._base)

        # Corporate actions client
        if self._enable_corporate:
            self.corporate_actions = CorporateActionsClient(self._base)

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
        """Stop clients, then delegate to ServiceApp for health + transport."""
        if self._rr is not None:
            await self._rr.close()
        await super().close()
