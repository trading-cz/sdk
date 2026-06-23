"""ServiceApp — minimal Kafka transport + health + shutdown wiring.

See _README.md for full documentation.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from tradingcz.sdk.health.publisher import HealthPublisher
from tradingcz.sdk.lang.async_utils import setup_shutdown_handlers
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


class ServiceApp:  # pylint: disable=too-many-instance-attributes
    """Minimal Kafka transport + health + shutdown wiring.  Compose clients on top."""

    def __init__(
        self,
        *,
        service_id: str,
        env: str,
        kafka_settings: KafkaSettings,
        health_interval: float = 300.0,
    ) -> None:
        self.service_id = service_id
        self._env = env
        self._health_interval = health_interval
        self._kafka = kafka_settings
        self._shutdown = asyncio.Event()

        self.topics = KafkaTopicRegistry(env=self._env)
        self.events_topic = self.topics.events.name
        self.events_producer = TransportProducer(self._kafka)
        self._faf = FireAndForget(TypedProducer(self.events_producer, self.events_topic), self.service_id)
        self._health = HealthPublisher(self._faf, self.service_id, interval=self._health_interval)
        self._topic_admin = KafkaTopicAdmin(self._kafka)

    # -- Lifecycle --

    async def start(self) -> None:
        """Ensure topics, emit INITIALIZING + READY, register shutdown handlers."""
        await self._topic_admin.ensure_from_config(self.topics.events)
        await self._health.initializing()
        await self._health.ready()
        setup_shutdown_handlers(self._shutdown)
        logger.info("ServiceApp started: id=%s env=%s", self.service_id, self._env)

    async def close(self) -> None:
        """Stop health (emits 'down'), flush and close producer, close admin."""
        if self._health is not None:
            await self._health.down()
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

    # -- Publishing --

    @property
    def faf(self) -> FireAndForget:
        """Fire-and-forget publisher — compose ``SignalPublisher(faf=app.faf)`` etc."""
        return self._faf

    async def publish_event(
        self,
        message: BaseModel,
        *,
        message_type: EventType,
        event_id: str = "",
        key: str = "",
    ) -> None:
        """Publish a typed message on the events channel (fire-and-forget)."""
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


__all__ = ["ServiceApp"]
