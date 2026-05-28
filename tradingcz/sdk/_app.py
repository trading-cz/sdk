"""TradingApp — batteries-included SDK entry point for strategies/consumers.

Configuration is driven by environment variables (see ``ServiceApp``).
Minimal setup — just provide a ``service_id``::

    from tradingcz.sdk import TradingApp

    async with TradingApp(service_id="my-strategy") as app:
        bars = await app.data.request_historical(["AAPL"])
        await app.signals.publish(signal)

Feature flags::

    app = TradingApp(service_id="risk-checker")
    app.with_signals(False).with_data(False)

Environment variables::

    KAFKA_BOOTSTRAP_SERVERS  — Kafka broker addresses (default: localhost:9092)
    KAFKA_CONSUMER_GROUP     — Consumer group id (default: <service_id>)
    SDK_ENV                  — Environment name (default: dev)
    SDK_BROKER               — Broker identifier (default: alpaca)
    SDK_HEALTH_INTERVAL      — Heartbeat interval in seconds (default: 300)
"""

from __future__ import annotations

import os

from tradingcz.sdk._helpers import _FireAndForget, _RequestReply
from tradingcz.sdk._service import ServiceApp
from tradingcz.sdk.balance import BalanceClient
from tradingcz.sdk.data import DataClient
from tradingcz.sdk.orders import OrderClient
from tradingcz.sdk.positions import PositionClient
from tradingcz.sdk.signals import SignalPublisher


class TradingApp(ServiceApp):  # pylint: disable=too-many-instance-attributes
    """Batteries-included trading application for strategy/consumer role.

    Extends ``ServiceApp`` with client APIs: data, signals, positions,
    balance, orders.  All features enabled by default — use
    ``.with_*(False)`` to disable.

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
        health_interval: float = 300.0,
    ) -> None:
        super().__init__(
            service_id=service_id,
            env=env,
            bootstrap_servers=bootstrap_servers,
            health_interval=health_interval,
        )
        self._broker = broker or os.environ.get("SDK_BROKER", "alpaca")

        self._enable_data = True
        self._enable_signals = True
        self._enable_positions = True
        self._enable_balance = True
        self._enable_orders = True

        # Set after start()
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

    def with_data(self, enable: bool = True) -> TradingApp:
        self._enable_data = enable
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
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize transport + client APIs."""
        await super().start()

        assert self.events_channel is not None
        assert self.transport is not None
        assert self.topics is not None

        # Shared internal helpers — use source_app for consistent header identity
        self._rr = _RequestReply(self.events_channel, self.source_app)
        self._faf = _FireAndForget(self.events_channel, self.source_app)
        await self._rr.start()

        # Data client
        if self._enable_data:
            self.data = DataClient(
                rr=self._rr,
                transport=self.transport,
                topics=self.topics,
                service_id=self.service_id,
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
        """Stop clients, then delegate to ServiceApp for health + transport."""
        if self._rr is not None:
            await self._rr.close()
        await super().close()
