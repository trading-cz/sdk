"""ServiceApp — common base for ALL trading services.

Handles the universal boilerplate that every service needs:
  - Kafka transport + topic registry
  - Events channel (shared for request/reply + lifecycle events)
  - HealthPublisher (up → heartbeat → down)
  - Graceful shutdown (signal handlers + resource cleanup)

Subclass for specific roles:
  - ``TradingApp``  — strategy/consumer role (data, signals, positions)
  - Provider apps    — provider/server role (request consumer, response producers)

Lifecycle::

    async with ServiceApp(service_id="my-app") as svc:
        # transport, topics, events_channel, health are ready
        await svc.events_channel.send(...)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from pydantic import BaseModel

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

    Provides transport, topic registry, events channel, health/heartbeat,
    and graceful shutdown.  Subclasses add role-specific APIs.

    Configuration via environment variables (all optional):
        ``KAFKA_BOOTSTRAP_SERVERS`` (default: localhost:9092)
        ``KAFKA_CONSUMER_GROUP``    (default: <service_id>)
        ``SDK_ENV``                 (default: dev)
        ``SDK_HEALTH_INTERVAL``     (default: 300)

    Args:
        service_id: Unique identifier for this instance.
        env: Deployment environment (dev/prd).  Env var: SDK_ENV.
        bootstrap_servers: Kafka broker addresses.  Env var: KAFKA_BOOTSTRAP_SERVERS.
        health_interval: Seconds between heartbeats.  Env var: SDK_HEALTH_INTERVAL.
    """

    def __init__(
        self,
        *,
        service_id: str,
        env: str | None = None,
        bootstrap_servers: str | None = None,
        health_interval: float = 300.0,
    ) -> None:
        self.service_id = service_id
        self._env = env or os.environ.get("SDK_ENV", "dev")
        self._health_interval = float(os.environ.get("SDK_HEALTH_INTERVAL", str(health_interval)))

        self._kafka = KafkaSettings(
            bootstrap_servers=bootstrap_servers
            or os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            consumer_group=os.environ.get("KAFKA_CONSUMER_GROUP", service_id),
        )

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
        """Initialize transport, topics, events channel, health.

        Subclasses should call ``await super().start()`` first,
        then wire their own components.
        """
        self.transport = KafkaTransport(self._kafka)
        self.topics = TopicRegistry(env=self._env)
        self.events_channel = await self.transport.channel(self.topics.events.name)

        # Health / heartbeat on the events channel
        self._faf = FireAndForget(self.events_channel, self.service_id)
        self._health = HealthPublisher(
            self._faf,
            self.service_id,
            interval=self._health_interval,
        )
        await self._health.start()

        # Signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._shutdown.set)
        except NotImplementedError:
            pass

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
    # Identity — used for headers, logging, health events
    # ------------------------------------------------------------------

    @property
    def source_app(self) -> str:
        """Service identifier for Kafka headers (same as ``service_id``)."""
        return self.service_id

    @property
    def env(self) -> str:
        """Deployment environment (dev/prd)."""
        return self._env

    async def publish(
        self,
        message: BaseModel,
        *,
        message_type: EventType,
        event_id: str = "",
        key: str = "",
    ) -> None:
        """Publish a typed message on the events channel (fire-and-forget).

        Convenience wrapper around ``FireAndForget`` — one-line send
        with standard headers.  The ``message_type`` and ``event_id``
        are required.

        Example::

            await self.publish(
                DataReady(event_id="...", ...),
                message_type=EventType.DATA_READY,
                event_id="abc-123",
            )
        """
        if self._faf is None:
            raise RuntimeError("Call start() before publish()")
        await self._faf.send_event(
            message, event_type=message_type, event_id=event_id, key=key
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def request_shutdown(self) -> None:
        """Signal the service to stop (used by signal handlers)."""
        self._shutdown.set()

    async def wait_for_shutdown(self) -> None:
        """Block until shutdown is requested (SIGTERM/SIGINT)."""
        await self._shutdown.wait()

    async def run_until_shutdown(self, *tasks: asyncio.Task[object]) -> None:
        """Run tasks until shutdown, then cancel them and close.

        Standard service lifecycle for server-type services::

            router_task = asyncio.create_task(router.run())
            await self.run_until_shutdown(router_task)

        On shutdown: cancels all tasks, awaits their cancellation,
        then calls ``close()`` (health 'down' + transport shutdown).
        """
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
