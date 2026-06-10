"""Health — publish own lifecycle events and monitor other services.

Two complementary classes sharing the same event topic:

- ``HealthPublisher`` — emit up/heartbeat/down for THIS service.
  Auto-enabled in every ``ServiceApp``.  Pushes events to Kafka.

- ``HealthMonitor`` — consume ServiceLifecycle events from OTHER services.
  Opt-in per service.  Calls ``on_down(service_id)`` when a service
  sends "down" or its heartbeat stops for longer than *ttl* seconds.
  Pulls events from Kafka.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from tradingcz.core.transport.kafka import KafkaChannel
from tradingcz.framework.helpers import FireAndForget
from tradingcz.models.headers import Header, MessageType, build_event_key
from tradingcz.models.health import ServiceLifecycle

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# HealthPublisher — emit lifecycle events for THIS service
# ═════════════════════════════════════════════════════════════════════════════


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
        faf: FireAndForget,
        service_id: str,
        interval: float = 300.0,
    ) -> None:
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

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None

        await self._emit("down")
        logger.info(
            "HealthPublisher stopped for %s (down event sent)", self._service_id
        )

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
        key = build_event_key(MessageType.SERVICE_LIFECYCLE, self._service_id, event)
        try:
            await self._faf.send(
                lifecycle,
                message_type=MessageType.SERVICE_LIFECYCLE,
                key=key,
                extra_headers={Header.LIFECYCLE_EVENT: event},
            )
            if event in ("up", "down"):
                logger.info(
                    "ServiceLifecycle sent: service=%s event=%s",
                    self._service_id,
                    event,
                )
            else:
                logger.debug(
                    "ServiceLifecycle sent: service=%s event=%s",
                    self._service_id,
                    event,
                )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to emit %s lifecycle event for %s",
                event,
                self._service_id,
                exc_info=True,
            )


# ═════════════════════════════════════════════════════════════════════════════
# HealthMonitor — consume lifecycle events from OTHER services
# ═════════════════════════════════════════════════════════════════════════════


class HealthMonitor:
    """Tracks liveness of other services.  Calls ``on_down`` on timeout.

    Consumes ``ServiceLifecycle`` events from the shared event channel.
    Two triggers fire the callback:
      - Explicit ``"down"`` event (graceful shutdown)
      - No heartbeat for > *ttl* seconds (crash / partition)

    Usage::

        monitor = HealthMonitor(events_channel, ttl=600)
        monitor.on_down(lambda sid: print(f"Service down: {sid}"))
        await monitor.start()
        ...
        await monitor.stop()
    """

    def __init__(
        self,
        channel: KafkaChannel,
        *,
        ttl: float = 600.0,
        sweep_interval: float = 60.0,
    ) -> None:
        self._channel = channel
        self._ttl = max(ttl, 1.0)
        self._sweep_interval = max(sweep_interval, 1.0)
        self._seen: dict[str, float] = {}  # service_id → time.monotonic()
        self._on_down: Callable[[str], Awaitable[None]] | None = None
        self._running = False
        self._consume_task: asyncio.Task[None] | None = None
        self._sweep_task: asyncio.Task[None] | None = None

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
        """Start consuming lifecycle events and the periodic sweep."""
        if self._running:
            return
        self._running = True
        self._consume_task = asyncio.create_task(self._consume())
        self._sweep_task = asyncio.create_task(self._sweep())

    async def stop(self) -> None:
        """Cancel background tasks."""
        if not self._running:
            return
        self._running = False
        for task in (self._consume_task, self._sweep_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._consume_task = None
        self._sweep_task = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _consume(self) -> None:
        """Read ServiceLifecycle events from the event channel."""
        try:
            async for msg in self._channel.receive(group_suffix="health"):
                if not self._running:
                    break
                if (
                    msg.headers.get(Header.MESSAGE_TYPE)
                    != MessageType.SERVICE_LIFECYCLE
                ):
                    continue
                try:
                    event = ServiceLifecycle.model_validate_json(msg.payload)
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
                sid = event.service_id
                if event.event == "down":
                    was_tracked = sid in self._seen
                    self._seen.pop(sid, None)
                    if was_tracked:
                        logger.info("HealthMonitor: %s reported down", sid)
                    await self._notify(sid)
                else:  # up or heartbeat
                    is_new = sid not in self._seen
                    self._seen[sid] = time.monotonic()
                    if is_new:
                        logger.info(
                            "HealthMonitor: %s is now alive (event=%s)",
                            sid,
                            event.event,
                        )
        except asyncio.CancelledError:
            pass

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
                            service_id,
                            now - last_seen,
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
                service_id,
                exc_info=True,
            )
