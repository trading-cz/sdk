"""HealthPublisher — emit lifecycle events for THIS service.

Used internally by ServiceApp.  Full API docs: health/_README.md
"""

from __future__ import annotations

import asyncio
import logging

from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.transport.kafka_key import KafkaKey

logger = logging.getLogger(__name__)


class HealthPublisher:
    """Publish service lifecycle events.  See health/_README.md."""

    def __init__(self, faf: FireAndForget, service_id: str, interval: float = 300.0) -> None:
        self._faf = faf
        self._service_id = service_id
        self._interval = max(interval, 1.0)
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the heartbeat loop is active."""
        return self._running

    async def initializing(self) -> None:
        """Emit INITIALIZING."""
        await self._emit(LifecycleEventType.INITIALIZING)

    async def ready(self) -> None:
        """Emit READY and start heartbeat loop."""
        if self._running:
            return
        await self._emit(LifecycleEventType.READY)
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("HealthPublisher ready for %s (interval=%ss)", self._service_id, self._interval)

    async def heartbeat(self) -> None:
        """Force heartbeat now and reset interval timer."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self._emit(LifecycleEventType.HEARTBEAT)
        if self._running:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def down(self) -> None:
        """Stop heartbeat and emit DOWN."""
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
        logger.info("HealthPublisher stopped for %s", self._service_id)

    async def _heartbeat_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._interval)
                if not self._running:
                    break
                await self._emit(LifecycleEventType.HEARTBEAT)
        except asyncio.CancelledError:
            pass

    async def _emit(self, event: LifecycleEventType) -> None:
        lifecycle = LifecycleEvent(service_id=self._service_id, event=event)
        key = KafkaKey(value=f"{EventType.SERVICE_LIFECYCLE}:{self._service_id}:{event}").to_kafka()
        try:
            await self._faf.send(lifecycle, event_type=EventType.SERVICE_LIFECYCLE, event_id=str(key), key=key)
            if event in (LifecycleEventType.INITIALIZING, LifecycleEventType.READY, LifecycleEventType.DOWN):
                logger.info("ServiceLifecycle sent: service=%s event=%s", self._service_id, event)
        except Exception:
            logger.warning("Failed to emit %s for %s", event, self._service_id, exc_info=True)


__all__ = ["HealthPublisher"]
