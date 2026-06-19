"""Unit tests for HealthMonitor."""

# pylint: disable=protected-access
# White-box tests: accessing _seen, _on_event, _ttl, _sweep_interval, _sweep_task is intentional.

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingcz.sdk.health.monitor import HealthMonitor
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent


class TestHealthMonitor:
    """Minimal unit tests for HealthMonitor — no Kafka, no real EventRouter."""

    @pytest.fixture
    def router(self) -> MagicMock:
        """Mock EventRouter — only needs ``on()`` to capture the handler."""
        router = MagicMock()
        router.on = MagicMock()
        return router

    @pytest.fixture
    def monitor(self, router: MagicMock) -> HealthMonitor:
        return HealthMonitor(router, ttl=10.0, sweep_interval=60.0)

    @pytest.fixture
    def raw_msg(self) -> MagicMock:
        return MagicMock()

    # ── Registration ───────────────────────────────────────────────────

    def test_registers_on_router(self, router: MagicMock) -> None:
        """HealthMonitor registers for SERVICE_LIFECYCLE events on the shared router."""
        HealthMonitor(router)
        router.on.assert_called_once()
        args = router.on.call_args[0]
        assert args[0] == EventType.SERVICE_LIFECYCLE
        assert args[1] == LifecycleEvent

    # ── UP event ───────────────────────────────────────────────────────

    async def test_up_event_tracks_service(
        self, monitor: HealthMonitor, raw_msg: MagicMock,
    ) -> None:
        """UP event → service is tracked as alive, no on_down callback."""
        cb = AsyncMock()
        monitor.on_down(cb)
        await monitor.start()

        await monitor._on_event(
            LifecycleEvent(service_id="s1", event=LifecycleEventType.UP), raw_msg,
        )
        assert "s1" in monitor._seen
        cb.assert_not_called()

        await monitor.stop()

    # ── HEARTBEAT event ────────────────────────────────────────────────

    async def test_heartbeat_refreshes_ttl(
        self, monitor: HealthMonitor, raw_msg: MagicMock,
    ) -> None:
        """HEARTBEAT → refreshes timestamp, no on_down callback."""
        cb = AsyncMock()
        monitor.on_down(cb)
        await monitor.start()

        await monitor._on_event(
            LifecycleEvent(service_id="s1", event=LifecycleEventType.HEARTBEAT), raw_msg,
        )
        assert "s1" in monitor._seen
        cb.assert_not_called()

        await monitor.stop()

    # ── DOWN event ─────────────────────────────────────────────────────

    async def test_down_event_fires_callback(
        self, monitor: HealthMonitor, raw_msg: MagicMock,
    ) -> None:
        """Explicit DOWN event → fires on_down callback."""
        cb = AsyncMock()
        monitor.on_down(cb)
        await monitor.start()

        # Track first, then send DOWN
        monitor._seen["s1"] = time.monotonic()
        await monitor._on_event(
            LifecycleEvent(service_id="s1", event=LifecycleEventType.DOWN), raw_msg,
        )
        assert "s1" not in monitor._seen
        cb.assert_called_once_with("s1")

        await monitor.stop()

    # ── TTL sweep ──────────────────────────────────────────────────────

    async def test_sweep_fires_callback_on_timeout(
        self, monitor: HealthMonitor,
    ) -> None:
        """Sweep → expired service fires on_down callback."""
        cb = AsyncMock()
        monitor.on_down(cb)
        monitor._ttl = 0.1          # tiny TTL
        monitor._sweep_interval = 0.05
        await monitor.start()

        # Track with an old timestamp
        monitor._seen["s1"] = time.monotonic() - 10.0
        await asyncio.sleep(0.15)   # let sweep run

        assert "s1" not in monitor._seen
        cb.assert_called_once_with("s1")

        await monitor.stop()

    # ── on_down callback error resilience ──────────────────────────────

    async def test_on_down_callback_exception_is_swallowed(
        self, monitor: HealthMonitor, raw_msg: MagicMock,
    ) -> None:
        """on_down callback that raises does not crash the monitor."""
        cb = AsyncMock(side_effect=RuntimeError("boom"))
        monitor.on_down(cb)
        await monitor.start()

        monitor._seen["s1"] = time.monotonic()
        await monitor._on_event(
            LifecycleEvent(service_id="s1", event=LifecycleEventType.DOWN), raw_msg,
        )
        # Should not raise — exception is swallowed
        cb.assert_called_once_with("s1")

        await monitor.stop()

    # ── Lifecycle: start/stop idempotency ──────────────────────────────

    async def test_double_start_is_idempotent(self, monitor: HealthMonitor) -> None:
        """Calling start() twice does not create duplicate sweep tasks."""
        await monitor.start()
        task1 = monitor._sweep_task
        await monitor.start()
        assert monitor._sweep_task is task1
        await monitor.stop()

    async def test_double_stop_is_idempotent(self, monitor: HealthMonitor) -> None:
        """Calling stop() twice is safe."""
        await monitor.start()
        await monitor.stop()
        await monitor.stop()  # should not raise
