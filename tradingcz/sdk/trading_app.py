"""TradingApp — batteries-included SDK entry point for strategies/consumers.

Configuration is driven by environment variables (see ``ServiceApp``).
Minimal setup — just provide a ``service_id``::

    from tradingcz.sdk import TradingApp

    async with TradingApp(service_id="my-strategy") as app:
        # One-time historical data
        bars = await app.stock.bars(["AAPL", "MSFT"], days=30)

        # Streaming data (context manager = guaranteed unsubscribe)
        async with app.stock.stream_quotes(["AAPL"]) as stream:
            async for quote in stream:
                if quote.quote.bid_price > threshold:
                    break

        # Publish a trading signal
        await app.signals.publish(signal, event_id="...")

Feature flags::

    app = TradingApp(service_id="risk-checker")
    app.with_signals(False).with_stock(False).with_options(False)

Multi-broker::

    async with TradingApp(service_id="arbitrage") as app:
        alpaca_bars = await app.stock.bars(["AAPL"])

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS  — Kafka broker addresses (default: localhost:9092)
    KAFKA_CONSUMER_GROUP     — Consumer group id (default: <service_id>)
    SDK_ENV                  — Environment name (default: dev)
    SDK_BROKER               — Broker identifier (default: alpaca)
    SDK_HEALTH_INTERVAL      — Heartbeat interval in seconds (default: 300)
"""

from __future__ import annotations

import logging

from tradingcz.sdk.account.balance import BalanceClient
from tradingcz.sdk.account.orders import OrderClient
from tradingcz.sdk.account.positions import PositionClient
from tradingcz.sdk.account.signals import SignalPublisher
from tradingcz.sdk.market_data._base import BaseDataClient
from tradingcz.sdk.market_data.corporate import CorporateActionsClient
from tradingcz.sdk.market_data.options import OptionsDataClient
from tradingcz.sdk.market_data.stock import StockDataClient
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.service_app import ServiceApp

logger = logging.getLogger(__name__)


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
    """Batteries-included trading application for strategy/consumer role."""

    def __init__(
        self,
        *,
        service_id: str,
        env: str,
        health_interval: float,
        broker: str = "alpaca",
    ) -> None:
        super().__init__(service_id=service_id, env=env, health_interval=health_interval)
        self._broker = broker

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
        """Enable/disable the options data client (snapshots)."""
        self._enable_options = enable
        return self

    def with_corporate_actions(self, enable: bool = True) -> TradingApp:
        """Enable/disable the corporate actions client (dividends, splits)."""
        self._enable_corporate = enable
        return self

    def with_signals(self, enable: bool = True) -> TradingApp:
        """Enable/disable the signal publisher."""
        self._enable_signals = enable
        return self

    def with_positions(self, enable: bool = True) -> TradingApp:
        """Enable/disable the position client."""
        self._enable_positions = enable
        return self

    def with_balance(self, enable: bool = True) -> TradingApp:
        """Enable/disable the balance client."""
        self._enable_balance = enable
        return self

    def with_orders(self, enable: bool = True) -> TradingApp:
        """Enable/disable the order client."""
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

        Each ``with_broker()`` call creates a fresh ``BaseDataClient``
        so deduplication and transport state are isolated per broker.
        """
        if self._rr is None or self.transport is None or self.topics is None:
            raise RuntimeError("Call start() before with_broker()")
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
        logger.info("TradingApp starting: id=%s broker=%s", self.service_id, self._broker)

        if self.events_channel is None or self.transport is None or self.topics is None:
            raise RuntimeError("ServiceApp.start() did not initialize transport")

        # Shared internal primitives
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

        if self._enable_stock:
            self.stock = StockDataClient(self._base)
            logger.info("TradingApp: stock client enabled")

        if self._enable_options:
            self.options = OptionsDataClient(self._base)
            logger.info("TradingApp: options client enabled")

        if self._enable_corporate:
            logger.info("TradingApp: corporate actions client enabled")
            self.corporate_actions = CorporateActionsClient(self._base)

        if self._enable_signals:
            if self._faf is None:
                raise RuntimeError("FireAndForget not initialized")
            logger.info("TradingApp: signal publisher enabled")
            self.signals = SignalPublisher(faf=self._faf)

        if self._enable_positions:
            if self._rr is None:
                raise RuntimeError("RequestReply not initialized")
            logger.info("TradingApp: position client enabled")
            self.positions = PositionClient(rr=self._rr)

        if self._enable_balance:
            if self._rr is None:
                raise RuntimeError("RequestReply not initialized")
            logger.info("TradingApp: balance client enabled")
            self.balance = BalanceClient(rr=self._rr)

        if self._enable_orders:
            if self._rr is None:
                raise RuntimeError("RequestReply not initialized")
            logger.info("TradingApp: order client enabled")
            self.orders = OrderClient(rr=self._rr)

        enabled = [
            name for name, flag in (
                ("stock", self._enable_stock),
                ("options", self._enable_options),
                ("corporate_actions", self._enable_corporate),
                ("signals", self._enable_signals),
                ("positions", self._enable_positions),
                ("balance", self._enable_balance),
                ("orders", self._enable_orders),
            ) if flag
        ]
        logger.info("TradingApp ready: id=%s broker=%s clients=[%s]",
                     self.service_id, self._broker, ", ".join(enabled))

    async def close(self) -> None:
        """Stop clients, then delegate to ServiceApp for health + transport."""
        logger.info("TradingApp closing: id=%s", self.service_id)
        if self._rr is not None:
            await self._rr.close()
        await super().close()


__all__ = ["TradingApp", "_BrokerScope"]
