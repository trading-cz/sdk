"""HealthMonitor — track liveness of other services.

Pure logic: no Kafka, no EventRouter.  Caller feeds events via on_event().
Full API docs: health/_README.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from tradingcz.sdk.models.enums.event import LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Track liveness of other services.  See health/_README.md."""

    def __init__(self, *, sweep_interval: float = 60.0) -> None:
        self._sweep_interval = max(sweep_interval, 1.0)
        self._ttl: float | None = None  # set via on() for EXPIRED
        self._seen: dict[str, float] = {}
        self._callbacks: dict[str, list[Callable[[str], Awaitable[None]]]] = {}
        self._running = False
        self._sweep_task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """Whether the monitor sweep loop is active."""
        return self._running

    def on(
        self,
        state: LifecycleEventType | str,
        callback: Callable[[str], Awaitable[None]],
        *,
        ttl: float | None = None,
    ) -> HealthMonitor:
        """Register callback for *state* (chainable).

        *ttl* is only meaningful for ``LifecycleEventType.EXPIRED`` —
        seconds without any event before a service is considered
        expired (default 600 if omitted).
        """
        if state == LifecycleEventType.EXPIRED:
            self._ttl = max(ttl or 600.0, 1.0)
        key = str(state)
        if key not in self._callbacks:
            self._callbacks[key] = []
        self._callbacks[key].append(callback)
        return self

    def on_event(self, event: LifecycleEvent) -> None:
        """Feed a lifecycle event.  Non-blocking — callbacks are create_task'd."""
        if not self._running:
            return
        sid = event.service_id
        if event.event == LifecycleEventType.DOWN:
            self._seen.pop(sid, None)
        else:
            is_new = sid not in self._seen
            self._seen[sid] = time.monotonic()
            if is_new:
                logger.info("HealthMonitor: %s is now alive (event=%s)", sid, event.event)
        asyncio.create_task(self._dispatch(event.event, sid))

    async def start(self) -> None:
        """Start TTL sweep."""
        if self._running:
            return
        self._running = True
        self._sweep_task = asyncio.create_task(self._sweep())

    async def stop(self) -> None:
        """Stop TTL sweep."""
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

    async def close(self) -> None:
        """Alias for :meth:`stop` — conforms to EventRouter convention."""
        await self.stop()

    async def _sweep(self) -> None:
        if self._ttl is None:
            return  # no EXPIRED callback registered, nothing to sweep
        try:
            while self._running:
                await asyncio.sleep(self._sweep_interval)
                if not self._running:
                    break
                now = time.monotonic()
                for service_id, last_seen in list(self._seen.items()):
                    if now - last_seen > self._ttl:
                        del self._seen[service_id]
                        logger.warning("HealthMonitor: %s timed out (last seen %.0fs ago)", service_id, now - last_seen)
                        await self._dispatch(LifecycleEventType.EXPIRED, service_id)
        except asyncio.CancelledError:
            pass

    async def _dispatch(self, state: str, service_id: str) -> None:
        for cb in self._callbacks.get(state, []):
            try:
                await cb(service_id)
            except Exception:
                logger.warning("HealthMonitor: callback failed state=%s service=%s", state, service_id, exc_info=True)


__all__ = ["HealthMonitor"]
