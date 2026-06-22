"""ServiceApp — common base for ALL trading services.

See _README.md for full documentation, usage examples, logging, and exception handling.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from tradingcz.sdk.account.signals import SignalPublisher

# Account clients (positions/balance/orders) disabled until executor supports them.
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

    Wires together Kafka transport, health, market data, and account
    clients.  All clients are created lazily on first access — no
    feature flags needed.  See _README.md for full docs.
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

        self.topics = KafkaTopicRegistry(env=self._env)
        self.events_topic = self.topics.events.name
        self.events_producer = TransportProducer(self._kafka)
        self._faf = FireAndForget(self.events_producer, self.events_topic, self.service_id)
        self._health = HealthPublisher(self._faf, self.service_id, interval=self._health_interval)
        self._topic_admin = KafkaTopicAdmin(self._kafka)

        self._rr: RequestReply | None = None
        self._base: BaseDataClient | None = None
        self._stock: StockDataClient | None = None
        self._options: OptionsDataClient | None = None
        self._corporate: CorporateActionsClient | None = None
        self._signals: SignalPublisher | None = None

        # Positions/Balance/Orders — disabled until executor implements handlers.

    # -- Lifecycle --

    async def start(self) -> None:
        """Create topics, emit INITIALIZING + READY, start RequestReply."""
        await self._topic_admin.ensure_from_config(self.topics.events)

        await self._health.initializing()

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

    # -- Kafka primitives --

    @property
    def kafka_settings(self) -> KafkaSettings:
        """Kafka connection settings — use with TypedConsumer, EventRouter, RequestReply."""
        return self._kafka

    @property
    def shutdown_event(self) -> asyncio.Event:
        """Event set on SIGTERM/SIGINT — use with ``run_until_shutdown()``."""
        return self._shutdown

    # -- Identity --

    @property
    def source_app(self) -> str:
        """Service identifier for Kafka headers."""
        return self.service_id

    # -- Market data clients (lazy) --

    @property
    def stock(self) -> StockDataClient:
        """Stock data client (bars, quotes, streaming).  Lazy — requires ``start()`` first."""
        if self._base is None:
            raise RuntimeError("Call start() before accessing stock client.")
        if self._stock is None:
            self._stock = StockDataClient(self._base)
        return self._stock

    @property
    def options(self) -> OptionsDataClient:
        """Options data client (snapshots).  Lazy — requires ``start()`` first."""
        if self._base is None:
            raise RuntimeError("Call start() before accessing options client.")
        if self._options is None:
            self._options = OptionsDataClient(self._base)
        return self._options

    @property
    def corporate_actions(self) -> CorporateActionsClient:
        """Corporate actions client (dividends, splits).  Lazy — requires ``start()`` first."""
        if self._base is None:
            raise RuntimeError("Call start() before accessing corporate actions client.")
        if self._corporate is None:
            self._corporate = CorporateActionsClient(self._base)
        return self._corporate

    # -- Account clients (lazy) --

    @property
    def signals(self) -> SignalPublisher:
        """Signal publisher (fire-and-forget).  Lazy — uses existing F&F transport."""
        if self._signals is None:
            self._signals = SignalPublisher(faf=self._faf)
        return self._signals

    # positions / balance / orders — disabled until executor supports them.

    # -- Multi-broker --

    def with_broker(self, broker: str) -> BrokerScope:
        """Return a BrokerScope with data clients scoped to *broker*."""
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

    # -- Publishing --

    async def publish_event(self, message: BaseModel, *, message_type: EventType, event_id: str = "", key: str = "") -> None:
        """Publish a typed message on the events channel (fire-and-forget)."""
        if not self._health.running:
            raise RuntimeError("Call start() before publish_event()")
        await self._faf.send(message, event_type=message_type, event_id=event_id, key=key)

    # -- Shutdown --

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


# -- BrokerScope --


class BrokerScope:
    """Broker-scoped client factory returned by ``ServiceApp.with_broker()``."""

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
