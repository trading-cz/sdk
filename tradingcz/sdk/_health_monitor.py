"""HealthMonitor — consume ServiceLifecycle events, track liveness.

Consumes ``ServiceLifecycle`` events from a Kafka channel and tracks
the last-seen timestamp per service.  A periodic sweep detects services
that have been silent longer than *ttl* and fires a callback.

Usage::

    monitor = HealthMonitor(channel, group_suffix="health", ttl=600)
    monitor.on_down(lambda sid: print(f"Service down: {sid}"))
    await monitor.start()
    # ... app runs ...
    await monitor.stop()

The monitor creates its own AIOConsumer with a stable consumer group
derived from *group_suffix*.  On restart the consumer resumes from the
last committed offset — no event is missed across restarts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from tradingcz.model.health import ServiceLifecycle
from tradingcz.transport.channel import KafkaChannel

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_TTL: float = 600.0  # 10 minutes = 2× default heartbeat interval
DEFAULT_SWEEP_INTERVAL: float = 60.0  # check for stale services every 60s
DEFAULT_IDLE_DRAIN: float = 2.0  # seconds of silence = "caught up" during replay


class HealthMonitor:
    """Tracks liveness of services via ServiceLifecycle events.

    Args:
        channel: Kafka channel to consume lifecycle events from.
        group_suffix: Suffix for the consumer group id (default ``"health"``).
        ttl: Seconds without heartbeat before a service is considered down.
        sweep_interval: Seconds between periodic TTL checks.

    Callbacks are registered via ``on_down()`` and invoked when a service
    goes down (explicit ``down`` event OR heartbeat timeout).
    """

    def __init__(
        self,
        channel: KafkaChannel,
        *,
        group_suffix: str = "health",
        ttl: float = DEFAULT_TTL,
        sweep_interval: float = DEFAULT_SWEEP_INTERVAL,
    ) -> None:
        self._channel = channel
        self._group_suffix = group_suffix
        self._ttl = max(ttl, 1.0)
        self._sweep_interval = max(sweep_interval, 1.0)

        self._last_seen: dict[str, float] = {}  # service_id → time.monotonic()
        self._on_down_callbacks: list[Callable[[str], Awaitable[None]]] = []

        self._running = False
        self._consume_task: asyncio.Task[None] | None = None
        self._sweep_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_down(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register *callback* to be invoked when a service is considered down.

        The callback receives the ``service_id`` of the downed service.
        Multiple callbacks can be registered — all are invoked in order.
        """
        self._on_down_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start consuming lifecycle events and the periodic sweep."""
        if self._running:
            return

        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())
        self._sweep_task = asyncio.create_task(self._sweep_loop())
        logger.info(
            "HealthMonitor started (ttl=%ss, sweep=%ss, group=%s)",
            self._ttl,
            self._sweep_interval,
            self._group_suffix,
        )

    async def stop(self) -> None:
        """Stop consuming and cancel background tasks."""
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
        logger.info("HealthMonitor stopped")

    # ------------------------------------------------------------------
    # Replay — read ALL events from beginning, return alive services
    # ------------------------------------------------------------------

    async def replay(self, *, idle_timeout: float = DEFAULT_IDLE_DRAIN) -> set[str]:
        """Replay ALL ServiceLifecycle events from the beginning of the topic.

        Creates a temporary consumer with a unique group id, drains all
        available messages, and returns the set of service_ids that are
        currently "alive" (last heartbeat within TTL).

        Use this during startup recovery to learn which services were
        running before we started.

        Args:
            idle_timeout: Seconds of silence that signals "caught up"
                (default 2.0).

        Returns:
            Set of ``service_id`` strings for services with a recent heartbeat.
        """
        import uuid

        # Unique group → starts from earliest offset (no committed offset)
        replay_group = f"{self._group_suffix}-replay-{uuid.uuid4().hex[:8]}"

        async for msg in self._channel.receive(
            group_suffix=replay_group,
            idle_timeout=idle_timeout,
        ):
            if not self._is_lifecycle(msg.headers.get("message_type", "")):
                continue

            try:
                event = ServiceLifecycle.model_validate_json(msg.payload)
            except Exception:
                continue

            self._apply_event(event)

        # After draining, determine which services are still alive
        now = time.monotonic()
        alive = {sid for sid, ts in self._last_seen.items() if now - ts <= self._ttl}

        logger.info(
            "HealthMonitor replay complete: %d services seen, %d alive",
            len(self._last_seen),
            len(alive),
        )
        return alive

    # ------------------------------------------------------------------
    # Internal: consume loop
    # ------------------------------------------------------------------

    async def _consume_loop(self) -> None:
        """Consume ServiceLifecycle events continuously.

        Uses a stable consumer group so that restarts resume from the
        last committed offset.
        """
        try:
            async for msg in self._channel.receive(group_suffix=self._group_suffix):
                if not self._running:
                    break

                if not self._is_lifecycle(msg.headers.get("message_type", "")):
                    continue

                try:
                    event = ServiceLifecycle.model_validate_json(msg.payload)
                except Exception:
                    logger.debug("Skipping unparseable lifecycle event", exc_info=True)
                    continue

                self._apply_event(event)

                # Explicit "down" → immediate trigger
                if event.event == "down":
                    await self._trigger_down(event.service_id)

        except asyncio.CancelledError:
            logger.debug("HealthMonitor consume loop cancelled")

    # ------------------------------------------------------------------
    # Internal: sweep loop
    # ------------------------------------------------------------------

    async def _sweep_loop(self) -> None:
        """Periodically check for services that exceeded TTL."""
        try:
            while self._running:
                await asyncio.sleep(self._sweep_interval)
                if not self._running:
                    break

                now = time.monotonic()
                timed_out: list[str] = []

                for service_id, last_seen in list(self._last_seen.items()):
                    if now - last_seen > self._ttl:
                        timed_out.append(service_id)

                for service_id in timed_out:
                    logger.warning(
                        "HealthMonitor: service %s timed out (last seen %.0fs ago)",
                        service_id,
                        now - self._last_seen.get(service_id, 0),
                    )
                    await self._trigger_down(service_id)

        except asyncio.CancelledError:
            logger.debug("HealthMonitor sweep loop cancelled")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_lifecycle(message_type: str) -> bool:
        return message_type == "service_lifecycle"

    def _apply_event(self, event: ServiceLifecycle) -> None:
        """Update last_seen from a lifecycle event."""
        if event.event in ("up", "heartbeat"):
            self._last_seen[event.service_id] = time.monotonic()
        elif event.event == "down":
            self._last_seen.pop(event.service_id, None)

    async def _trigger_down(self, service_id: str) -> None:
        """Call all registered on_down callbacks."""
        self._last_seen.pop(service_id, None)
        for cb in self._on_down_callbacks:
            try:
                await cb(service_id)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "HealthMonitor: on_down callback failed for %s",
                    service_id,
                    exc_info=True,
                )
