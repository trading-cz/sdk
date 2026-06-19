"""HealthPublisher — emit lifecycle events (up/heartbeat/down) for THIS service.

Used internally by ``ServiceApp``.  Pushes events to Kafka.
"""

from __future__ import annotations

import asyncio
import logging

from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.transport.keys import KafkaKey
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
        await health.start()    # emits "up"
        # ... app runs ...
        await health.close()    # emits "down"
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

    async def start(self) -> None:
        """Send ``up`` event and start the periodic heartbeat task."""
        if self._running:
            return

        await self._emit(LifecycleEventType.UP)
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("HealthPublisher started for %s (interval=%ss)", self._service_id, self._interval)

    async def close(self) -> None:
        """Stop heartbeat and send ``down`` event."""
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
        logger.info( "HealthPublisher stopped for %s (down event sent)", self._service_id )

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
        """Send a LifecycleEvent event via fire-and-forget."""
        lifecycle = LifecycleEvent(
            service_id=self._service_id,
            event=event,
        )
        key = KafkaKey(value=f"{EventType.SERVICE_LIFECYCLE}:{self._service_id}:{event}").to_kafka()
        try:
            await self._faf.send_event(lifecycle, event_type=EventType.SERVICE_LIFECYCLE, event_id=str(key), key=key)
            if event in (LifecycleEventType.UP, LifecycleEventType.DOWN):
                logger.info("ServiceLifecycle sent: service=%s event=%s", self._service_id, event,)
            else:
                logger.debug("ServiceLifecycle sent: service=%s event=%s", self._service_id, event)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to emit %s lifecycle event for %s", event, self._service_id, exc_info=True)


__all__ = ["HealthPublisher"]

