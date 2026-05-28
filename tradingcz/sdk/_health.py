"""HealthPublisher — periodic heartbeat + lifecycle events.

Emits ``ServiceLifecycle`` events on the shared event topic so the
platform can track which services are running.

- ``up`` on start
- ``heartbeat`` every *interval* seconds (default 300 = 5 minutes)
- ``down`` on close

Used internally by ``TradingApp``.  Not part of the public API.
"""

from __future__ import annotations

import asyncio
import logging

from tradingcz.model.health import ServiceLifecycle
from tradingcz.sdk._helpers import _FireAndForget

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

    def __init__(
        self,
        faf: _FireAndForget,
        service_id: str,
        interval: float = 300.0,
    ) -> None:
        self._faf = faf
        self._service_id = service_id
        self._interval = max(interval, 1.0)  # minimum 1 second
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Send ``up`` event and start the periodic heartbeat task."""
        if self._running:
            return

        await self._emit("up")
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "HealthPublisher started for %s (interval=%ss)",
            self._service_id,
            self._interval,
        )

    async def close(self) -> None:
        """Stop heartbeat and send ``down`` event."""
        if not self._running:
            return

        self._running = False

        # Cancel the heartbeat loop
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None

        # Emit final "down" event — flush to guarantee delivery
        await self._emit("down")
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
                await self._emit("heartbeat")
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled for %s", self._service_id)

    async def _emit(self, event: str) -> None:
        """Send a ServiceLifecycle event via fire-and-forget."""
        lifecycle = ServiceLifecycle(
            service_id=self._service_id,
            event=event,  # type: ignore[arg-type]
        )
        try:
            await self._faf.send(
                lifecycle,
                message_type="service_lifecycle",
                key=self._service_id,
                extra_headers={"lifecycle_event": event},
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to emit %s lifecycle event for %s",
                event,
                self._service_id,
                exc_info=True,
            )
