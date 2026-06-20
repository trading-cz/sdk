"""HealthMonitor — track liveness of other services via shared EventRouter.

Tracks liveness of other services.  Calls ``on_down`` on timeout.

Registers on a shared :class:`~tradingcz.sdk.messaging.router.EventRouter`
for ``SERVICE_LIFECYCLE`` events instead of opening its own Kafka consumer.
This means the monitor and all other event handlers share exactly one
consumer on the events topic — no duplicate consumer groups.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from tradingcz.sdk.messaging.router import EventRouter
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.transport.kafka_message import KafkaMessage

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(
        self,
        router: EventRouter,
        *,
        ttl: float = 600.0,
        sweep_interval: float = 60.0,
    ) -> None:
        self._ttl = max(ttl, 1.0)
        self._sweep_interval = max(sweep_interval, 1.0)
        self._seen: dict[str, float] = {}  # service_id → time.monotonic()
        self._on_down: Callable[[str], Awaitable[None]] | None = None
        self._running = False
        self._sweep_task: asyncio.Task[None] | None = None

        # Register on the shared EventRouter — no separate Kafka consumer.
        router.on(
            EventType.SERVICE_LIFECYCLE,
            LifecycleEvent,
            handler=self._on_event,
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def on_down(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register the callback invoked when a service is considered down."""
        self._on_down = callback

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the periodic TTL sweep."""
        if self._running:
            return
        self._running = True
        self._sweep_task = asyncio.create_task(self._sweep())

    async def stop(self) -> None:
        """Cancel the sweep task.  Event dispatch stops when EventRouter.run() exits."""
        if not self._running:
            return
        self._running = False
        if self._sweep_task and not self._sweep_task.done():
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
        self._sweep_task = None
        self._seen.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _on_event(self, event: LifecycleEvent, _raw: KafkaMessage) -> None:
        """Called by EventRouter for each SERVICE_LIFECYCLE event."""
        if not self._running:
            return
        sid = event.service_id
        if event.event == LifecycleEventType.DOWN:
            was_tracked = sid in self._seen
            self._seen.pop(sid, None)
            if was_tracked:
                logger.info("HealthMonitor: %s reported down", sid)
            await self._notify(sid)
        else:  # initializing, ready, or heartbeat
            is_new = sid not in self._seen
            self._seen[sid] = time.monotonic()
            if is_new:
                logger.info(
                    "HealthMonitor: %s is now alive (event=%s)",
                    sid, event.event,
                )

    async def _sweep(self) -> None:
        """Periodically check for services past TTL."""
        try:
            while self._running:
                await asyncio.sleep(self._sweep_interval)
                if not self._running:
                    break
                now = time.monotonic()
                for service_id, last_seen in list(self._seen.items()):
                    if now - last_seen > self._ttl:
                        del self._seen[service_id]
                        logger.warning(
                            "HealthMonitor: %s timed out (last seen %.0fs ago)",
                            service_id, now - last_seen,
                        )
                        await self._notify(service_id)
        except asyncio.CancelledError:
            pass

    async def _notify(self, service_id: str) -> None:
        """Call the on_down callback, swallowing exceptions."""
        if self._on_down is None:
            return
        try:
            await self._on_down(service_id)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "HealthMonitor: on_down callback failed for %s",
                service_id, exc_info=True,
            )


__all__ = ["HealthMonitor"]

