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
from tradingcz.sdk.transport.channel import KafkaChannel
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.topics import TopicRegistry
from tradingcz.sdk.transport.transport import KafkaTransport

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
        self.topics: TopicRegistry | None = None
        self.events_channel: KafkaChannel | None = None
        self._faf: FireAndForget | None = None
        self._health: HealthPublisher | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize transport, topics, events channel, health."""
        self.transport = KafkaTransport(self._kafka)
        self.topics = TopicRegistry(env=self._env)
        self.events_channel = await self.transport.channel(self.topics.events.name)

        self._faf = FireAndForget(self.events_channel, self.service_id)
        self._health = HealthPublisher(self._faf, self.service_id, interval=self._health_interval)
        await self._health.start()

        setup_shutdown_handlers(self._shutdown)
        logger.info("ServiceApp started: id=%s env=%s", self.service_id, self._env)

    async def close(self) -> None:
        """Stop health (emits 'down'), close transport."""
        if self._health is not None:
            await self._health.close()
        if self.transport is not None:
            await self.transport.close()
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
