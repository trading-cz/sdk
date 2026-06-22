"""ServiceApp — common base for ALL trading services.

Handles: Kafka transport, events producer, health/heartbeat, graceful shutdown.

All clients are created lazily on first access — no feature flags needed.
RequestReply + BaseDataClient are always started (one consumer group overhead
is negligible for the platform scale).

Lifecycle::

    async with ServiceApp(service_id="my-app", env="dev", kafka_settings=KafkaSettings(consumer_group="my-app")) as svc:
        # ── Publish events (fire-and-forget) ──────────────────────
        await svc.publish_event(
            some_model,
            message_type=EventType.SERVICE_LIFECYCLE,
            event_id="evt-001",
        )

        # ── Market data (lazy — created on first access) ──────────
        bars = await svc.stock.bars(["AAPL"], days=30)

        # ── Signals (fire-and-forget, no RequestReply needed) ─────
        await svc.signals.publish(signal, event_id="evt-1")

        # ── Access Kafka primitives for TypedConsumer / EventRouter ─
        consumer = TypedConsumer(
            topic=svc.events_topic,
            settings=svc.kafka_settings,
            types={...},
            group_suffix="my-consumer",
        )

        # ── Run until SIGTERM/SIGINT, then cancel tasks ───────────
        await svc.run_until_shutdown(router_task)
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from tradingcz.sdk.account.signals import SignalPublisher

# NOTE: PositionClient, BalanceClient, OrderClient are implemented
# in the SDK but not yet backed by executor handlers. Disabled until
# executor gains get_positions / get_balance / get_orders support.
# from tradingcz.sdk.account.balance import BalanceClient
# from tradingcz.sdk.account.orders import OrderClient
# from tradingcz.sdk.account.positions import PositionClient
from tradingcz.sdk.health.publisher import HealthPublisher
from tradingcz.sdk.lang.async_utils import setup_shutdown_handlers
from tradingcz.sdk.market_data._base import BaseDataClient
from tradingcz.sdk.market_data.corporate import CorporateActionsClient
from tradingcz.sdk.market_data.options import OptionsDataClient
from tradingcz.sdk.market_data.stock import StockDataClient
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer

logger = logging.getLogger(__name__)


class ServiceApp:  # pylint: disable=too-many-instance-attributes
    """Base class for every service in the trading platform.

    **Minimal usage** (Kafka transport + health only)::

        async with ServiceApp(service_id="my-service", env="dev", kafka_settings=KafkaSettings(consumer_group="my-service")) as svc:
            await svc.publish_event(...)
            await svc.run_until_shutdown(router_task)

    **Strategy usage** (market data + signals)::

        async with ServiceApp(service_id="my-strategy", env="dev", kafka_settings=KafkaSettings(consumer_group="my-strategy")) as app:
            bars = await app.stock.bars(["AAPL"], days=30)
            await app.signals.publish(signal, event_id="evt-1")

    **Multi-broker**::

        async with ServiceApp(service_id="arb", env="dev", kafka_settings=KafkaSettings(consumer_group="arb")) as app:
            ibkr = app.with_broker("ibkr")
            ibkr_bars = await ibkr.stock.bars(["AAPL"], days=30)

    All clients are created lazily on first access — no feature flags needed.
    RequestReply + BaseDataClient are always started in :meth:`start`.

    Args:
        service_id: Unique identifier for this instance.
        env: Deployment environment (dev/prd) — scopes topic names.
        health_interval: Seconds between heartbeats (default 300).
        kafka_settings: Pre-configured Kafka settings.  If ``None``
            (default), reads from ``KAFKA_*`` environment variables.
            ``consumer_group`` defaults to *service_id* when not
            explicitly set on the passed-in settings.
        broker: Default broker for data clients (default ``"alpaca"``).
    """

    def __init__(
        self,
        *,
        service_id: str,
        env: str,
        kafka_settings: KafkaSettings,
        health_interval: float = 300.0,
        broker: str = "alpaca",
    ) -> None:
        self.service_id = service_id
        self._env = env
        self._health_interval = health_interval
        self._broker = broker
        self._kafka = kafka_settings
        self._shutdown = asyncio.Event()

        # ── Kafka transport + messaging (sync init) ──────────────────────
        self.topics = KafkaTopicRegistry(env=self._env)
        self.events_topic = self.topics.events.name
        self.events_producer = TransportProducer(self._kafka)
        self._faf = FireAndForget(self.events_producer, self.events_topic, self.service_id)
        self._health = HealthPublisher(self._faf, self.service_id, interval=self._health_interval)
        self._topic_admin = KafkaTopicAdmin(self._kafka)

        # Set by start() (async init)
        self._rr: RequestReply | None = None
        self._base: BaseDataClient | None = None

        # Lazy client slots — created on first access
        self._stock: StockDataClient | None = None
        self._options: OptionsDataClient | None = None
        self._corporate: CorporateActionsClient | None = None
        self._signals: SignalPublisher | None = None

        # NOTE: Disabled until executor implements handlers for:
        #   get_positions / get_balance / get_orders
        # self._positions: PositionClient | None = None
        # self._balance: BalanceClient | None = None
        # self._orders: OrderClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Ensure topics exist, emit INITIALIZING + READY, start RequestReply.

        RequestReply + BaseDataClient are always created (single consumer
        group overhead is negligible at platform scale).  Individual data
        clients (stock, options, corporate, signals) are created lazily
        on first access.
        """
        await self._topic_admin.ensure_from_config(self.topics.events)

        await self._health.initializing()

        # ── Request/Reply + BaseDataClient (always — cheap at our scale) ──
        self._rr = RequestReply(
            producer=self.events_producer,
            topic=self.events_topic,
            settings=self._kafka,
            service_id=self.service_id,
            group_suffix="svc-reply",
        )
        await self._rr.start()
        self._base = BaseDataClient(
            rr=self._rr,
            settings=self._kafka,
            topics=self.topics,
            service_id=self.service_id,
            broker=self._broker,  # type: ignore[arg-type]
        )
        logger.info("ServiceApp: RequestReply + BaseDataClient ready")

        await self._health.ready()
        setup_shutdown_handlers(self._shutdown)
        logger.info("ServiceApp started: id=%s env=%s", self.service_id, self._env)

    async def close(self) -> None:
        """Stop health (emits 'down'), close RR, flush producer."""
        if self._health is not None:
            await self._health.down()
        if self._rr is not None:
            await self._rr.close()
        if self.events_producer is not None:
            await self.events_producer.close()
        if self._topic_admin is not None:
            await self._topic_admin.close()
        logger.info("ServiceApp closed: id=%s", self.service_id)

    async def __aenter__(self) -> ServiceApp:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Kafka primitives (for TypedConsumer, EventRouter, etc.)
    # ------------------------------------------------------------------

    @property
    def kafka_settings(self) -> KafkaSettings:
        """Kafka connection settings — use with TypedConsumer, EventRouter, RequestReply."""
        return self._kafka

    @property
    def shutdown_event(self) -> asyncio.Event:
        """Event set on SIGTERM/SIGINT — use with ``run_until_shutdown()``."""
        return self._shutdown

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def source_app(self) -> str:
        """Service identifier for Kafka headers."""
        return self.service_id

    # ------------------------------------------------------------------
    # Market data clients (lazy — created on first access)
    # ------------------------------------------------------------------

    @property
    def stock(self) -> StockDataClient:
        """Stock data client — bars, quotes, trades, streaming.

        Created lazily on first access.  Requires :meth:`start` to have
        been called first.
        """
        if self._base is None:
            raise RuntimeError("Call start() before accessing stock client.")
        if self._stock is None:
            self._stock = StockDataClient(self._base)
        return self._stock

    @property
    def options(self) -> OptionsDataClient:
        """Options data client — snapshots.

        Created lazily on first access.  Requires :meth:`start` to have
        been called first.
        """
        if self._base is None:
            raise RuntimeError("Call start() before accessing options client.")
        if self._options is None:
            self._options = OptionsDataClient(self._base)
        return self._options

    @property
    def corporate_actions(self) -> CorporateActionsClient:
        """Corporate actions client — dividends, splits.

        Created lazily on first access.  Requires :meth:`start` to have
        been called first.
        """
        if self._base is None:
            raise RuntimeError("Call start() before accessing corporate actions client.")
        if self._corporate is None:
            self._corporate = CorporateActionsClient(self._base)
        return self._corporate

    # ------------------------------------------------------------------
    # Account clients (lazy — created on first access)
    # ------------------------------------------------------------------

    @property
    def signals(self) -> SignalPublisher:
        """Signal publisher — fire-and-forget trading signals.

        Created lazily on first access.  Uses the existing
        :class:`FireAndForget` transport (no RequestReply needed).
        """
        if self._signals is None:
            self._signals = SignalPublisher(faf=self._faf)
        return self._signals

    # NOTE: PositionClient, BalanceClient, OrderClient are implemented
    # in the SDK but not yet backed by executor handlers.
    # Disabled until executor gains get_positions / get_balance / get_orders support.
    #
    # @property
    # def positions(self) -> PositionClient: ...
    #
    # @property
    # def balance(self) -> BalanceClient: ...
    #
    # @property
    # def orders(self) -> OrderClient: ...

    # ------------------------------------------------------------------
    # Multi-broker
    # ------------------------------------------------------------------

    def with_broker(self, broker: str) -> BrokerScope:
        """Return a broker-scoped client factory.

        Creates data clients that talk to *broker* instead of the
        default broker.  Useful for multi-broker strategies::

            async with ServiceApp(service_id="arb", env="dev", kafka_settings=KafkaSettings(consumer_group="arb")) as app:
                ibkr = app.with_broker("ibkr")
                ibkr_bars = await ibkr.stock.bars(["AAPL"], days=30)
        """
        if self._rr is None or self._base is None:
            raise RuntimeError("Call start() before with_broker()")
        base = BaseDataClient(
            rr=self._rr,
            settings=self._kafka,
            topics=self.topics,  # type: ignore[arg-type]
            service_id=self.service_id,
            broker=broker,  # type: ignore[arg-type]
        )
        return BrokerScope(base)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_event(self, message: BaseModel, *, message_type: EventType, event_id: str = "", key: str = "") -> None:
        """Publish a typed message on the events channel (fire-and-forget)."""
        if not self._health.running:
            raise RuntimeError("Call start() before publish_event()")
        await self._faf.send(message, event_type=message_type, event_id=event_id, key=key)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def request_shutdown(self) -> None:
        """Signal the service to stop."""
        self._shutdown.set()

    async def wait_for_shutdown(self) -> None:
        """Block until shutdown is requested."""
        await self._shutdown.wait()

    async def run_until_shutdown(self, *tasks: asyncio.Task[object]) -> None:
        """Run tasks until shutdown, cancel them, then close."""
        await self._shutdown.wait()
        logger.info("Shutdown requested — cancelling %d task(s)", len(tasks))
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.close()


# ------------------------------------------------------------------
# BrokerScope — broker-scoped client factory for with_broker()
# ------------------------------------------------------------------


class BrokerScope:
    """Lightweight broker-scoped client factory.

    Returned by ``ServiceApp.with_broker("ibkr")``.  Creates data
    clients that talk to the specified broker instead of the default.
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base
        self._stock: StockDataClient | None = None
        self._options: OptionsDataClient | None = None
        self._corporate: CorporateActionsClient | None = None

    @property
    def stock(self) -> StockDataClient:
        """Stock data client scoped to this broker."""
        if self._stock is None:
            self._stock = StockDataClient(self._base)
        return self._stock

    @property
    def options(self) -> OptionsDataClient:
        """Options data client scoped to this broker."""
        if self._options is None:
            self._options = OptionsDataClient(self._base)
        return self._options

    @property
    def corporate_actions(self) -> CorporateActionsClient:
        """Corporate actions client scoped to this broker."""
        if self._corporate is None:
            self._corporate = CorporateActionsClient(self._base)
        return self._corporate


__all__ = ["ServiceApp", "BrokerScope"]


__all__ = ["ServiceApp"]
