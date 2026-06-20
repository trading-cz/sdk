"""HealthPublisher — emit lifecycle events for THIS service.

Used internally by ``ServiceApp``.  Pushes events to Kafka via
``FireAndForget``.

Lifecycle sequence::

    health.initializing()   → INITIALIZING
    # ... app init / recovery ...
    health.ready()          → READY + heartbeat loop starts
    # ... app runs ...
    health.down()           → DOWN + heartbeat loop stops
"""

from __future__ import annotations

import asyncio
import logging

from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent

logger = logging.getLogger(__name__)


class HealthPublisher:
    """Publish service lifecycle events on the event topic.

    Args:
        faf: Fire-and-forget sender bound to the events channel.
        service_id: Unique identifier for this service instance.
        interval: Seconds between heartbeat events (default 300 = 5 min).

    Usage::

        health = HealthPublisher(faf, "my-strategy", interval=300)
        await health.initializing()   # emit INITIALIZING
        # ... init ...
        await health.ready()          # emit READY, start heartbeat
        # ... app runs ...
        await health.down()           # stop heartbeat, emit DOWN
    """

    def __init__(self, faf: FireAndForget, service_id: str, interval: float = 300.0) -> None:
        self._faf = faf
        self._service_id = service_id
        self._interval = max(interval, 1.0)
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initializing(self) -> None:
        """Send ``INITIALIZING`` event.

        Call once, early in startup, as soon as the Kafka producer
        is ready.  Does NOT start the heartbeat loop.
        """
        await self._emit(LifecycleEventType.INITIALIZING)

    async def ready(self) -> None:
        """Send ``READY`` event and start the periodic heartbeat loop.

        Call once, after all initialization (including recovery) is
        complete.  Heartbeat begins AFTER this call — a service that
        never reaches ``ready()`` will not send heartbeats and will
        be swept by ``HealthMonitor``'s TTL.
        """
        if self._running:
            return
        await self._emit(LifecycleEventType.READY)
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("HealthPublisher ready for %s (heartbeat interval=%ss)", self._service_id, self._interval)

    async def down(self) -> None:
        """Stop heartbeat and send ``DOWN`` event.

        Call once on graceful shutdown.  Safe to call multiple times.
        """
        if not self._running:
            return

        self._running = False

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None

        await self._emit(LifecycleEventType.DOWN)
        logger.info("HealthPublisher stopped for %s (down event sent)", self._service_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat task."""
        try:
            while self._running:
                await asyncio.sleep(self._interval)
                if not self._running:
                    break
                await self._emit(LifecycleEventType.HEARTBEAT)
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled for %s", self._service_id)

    async def _emit(self, event: LifecycleEventType) -> None:
        """Send a LifecycleEvent via fire-and-forget."""
        lifecycle = LifecycleEvent(
            service_id=self._service_id,
            event=event,
        )
        key = KafkaKey(value=f"{EventType.SERVICE_LIFECYCLE}:{self._service_id}:{event}").to_kafka()
        try:
            await self._faf.send(lifecycle, event_type=EventType.SERVICE_LIFECYCLE, event_id=str(key), key=key)
            if event in (LifecycleEventType.INITIALIZING, LifecycleEventType.READY, LifecycleEventType.DOWN):
                logger.info("ServiceLifecycle sent: service=%s event=%s", self._service_id, event)
            else:
                logger.debug("ServiceLifecycle sent: service=%s event=%s", self._service_id, event)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to emit %s lifecycle event for %s", event, self._service_id, exc_info=True)


__all__ = ["HealthPublisher"]
