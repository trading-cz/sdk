"""TradingApp — batteries-included SDK entry point.

Usage — all features enabled by default::

    from tradingcz.sdk import TradingApp

    app = (TradingApp(env="dev", service_id="my-strategy")
           .build())
    await app.start()

    bars = await app.data.request_historical(["AAPL"])
    await app.close()

Usage — selective features::

    app = (TradingApp(env="dev", service_id="risk-checker")
           .with_data(False)
           .with_signals(False)
           .build())
    await app.start()
    # Only app.positions, app.balance, app.orders available
"""

from __future__ import annotations

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
    """Builder for a fully wired trading application.

    All client features are enabled by default.  Use ``.with_*(False)``
    to disable features you don't need.
    """

    def __init__(
        self,
        *,
        env: str = "dev",
        service_id: str,
        bootstrap_servers: str = "localhost:9092",
        broker: str = "alpaca",
    ) -> None:
        self._env = env
        self._service_id = service_id
        self._bootstrap_servers = bootstrap_servers
        self._broker = broker
        self._enable_data = True
        self._enable_signals = True
        self._enable_positions = True
        self._enable_balance = True
        self._enable_orders = True
        self._built = False

        # Set after build()/start()
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

    def build(self) -> "TradingApp":
        """Validate and freeze configuration. Call before start()."""
        self._built = True
        return self

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize transport and enabled clients."""
        if not self._built:
            raise RuntimeError("Call .build() before .start()")

        settings = KafkaSettings(
            bootstrap_servers=self._bootstrap_servers,
            consumer_group=self._service_id,
        )
        self._transport = KafkaTransport(settings)
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
        """Graceful shutdown."""
        if self._rr is not None:
            await self._rr.close()
        if self._transport is not None:
            await self._transport.close()
