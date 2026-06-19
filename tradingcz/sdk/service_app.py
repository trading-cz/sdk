"""ServiceApp — common base for ALL trading services.

Handles: Kafka transport, events channel, health/heartbeat, graceful shutdown.

Lifecycle::

    async with ServiceApp(service_id="my-app", env="dev", health_interval=300) as svc:
        await svc.events_channel.send(...)
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from tradingcz.sdk.lang.async_utils import setup_shutdown_handlers
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.messaging.health_publisher import HealthPublisher
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry

logger = logging.getLogger(__name__)


class ServiceApp:
    """Base class for every service in the trading platform.

    Args:
        service_id: Unique identifier for this instance.
        env: Deployment environment (dev/prd) — scopes topic names.
        health_interval: Seconds between heartbeats.
    """

    def __init__(
        self,
        *,
        service_id: str,
        env: str,
        health_interval: float,
    ) -> None:
        self.service_id = service_id
        self._env = env
        self._health_interval = health_interval

        self._kafka = KafkaSettings(consumer_group=service_id)
        self._shutdown = asyncio.Event()

        # Set by start()
        self.transport: KafkaTransport | None = None
        self.topics: KafkaTopicRegistry | None = None
        self.events_producer: TransportProducer | None = None
        self.events_topic: str = ""
        self._faf: FireAndForget | None = None
        self._health: HealthPublisher | None = None
        self._topic_admin: KafkaTopicAdmin | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize topics, events producer, health."""
        self.topics = KafkaTopicRegistry(env=self._env)
        self.events_topic = self.topics.events.name
        self._topic_admin = KafkaTopicAdmin(self._kafka)
        await self._topic_admin.ensure_from_config(self.topics.events)
        self.events_producer = TransportProducer(self._kafka)

        self._faf = FireAndForget(self.events_producer, self.events_topic, self.service_id)
        self._health = HealthPublisher(self._faf, self.service_id, interval=self._health_interval)
        await self._health.start()

        setup_shutdown_handlers(self._shutdown)
        logger.info("ServiceApp started: id=%s env=%s", self.service_id, self._env)

    async def close(self) -> None:
        """Stop health (emits 'down'), flush producer."""
        if self._health is not None:
            await self._health.close()
        if self.events_producer is not None:
            await self.events_producer.flush()
        if self._topic_admin is not None:
            self._topic_admin.close()
        logger.info("ServiceApp closed: id=%s", self.service_id)

    async def __aenter__(self) -> ServiceApp:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def source_app(self) -> str:
        """Service identifier for Kafka headers."""
        return self.service_id

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_event(self, message: BaseModel, *, message_type: EventType, event_id: str = "", key: str = "") -> None:
        """Publish a typed message on the events channel (fire-and-forget)."""
        if self._faf is None:
            raise RuntimeError("Call start() before publish_event()")
        await self._faf.send_event(message, event_type=message_type, event_id=event_id, key=key)

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


__all__ = ["ServiceApp"]
