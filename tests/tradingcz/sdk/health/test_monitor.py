"""Unit tests for HealthMonitor."""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from tradingcz.sdk.health.monitor import HealthMonitor
from tradingcz.sdk.models.enums.event import LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent


class TestHealthMonitor:
    """Minimal unit tests for HealthMonitor — no Kafka, no EventRouter."""

    @pytest.fixture
    def monitor(self) -> HealthMonitor:
        return HealthMonitor(sweep_interval=60.0)

    # ── Registration ───────────────────────────────────────────────────

    def test_on_is_chainable(self, monitor: HealthMonitor) -> None:
        result = monitor.on(LifecycleEventType.DOWN, AsyncMock())
        assert result is monitor

    def test_ttl_is_set_on_expired_registration(self, monitor: HealthMonitor) -> None:
        """Registering EXPIRED with ttl sets the monitor's TTL."""
        assert monitor._ttl is None
        monitor.on(LifecycleEventType.EXPIRED, AsyncMock(), ttl=300)
        assert monitor._ttl == 300.0

    def test_ttl_defaults_to_600_when_omitted(self, monitor: HealthMonitor) -> None:
        """EXPIRED without explicit ttl defaults to 600."""
        monitor.on(LifecycleEventType.EXPIRED, AsyncMock())
        assert monitor._ttl == 600.0

    def test_ttl_not_set_for_non_expired_states(self, monitor: HealthMonitor) -> None:
        """Non-EXPIRED registrations don't affect TTL."""
        monitor.on(LifecycleEventType.READY, AsyncMock())
        assert monitor._ttl is None

    # ── INITIALIZING event ─────────────────────────────────────────────

    async def test_initializing_fires_callback(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.INITIALIZING, cb)
        await monitor.start()

        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.INITIALIZING))
        await asyncio.sleep(0.01)

        assert "s1" in monitor._seen
        cb.assert_called_once_with("s1")
        await monitor.stop()

    async def test_initializing_does_not_fire_other_states(self, monitor: HealthMonitor) -> None:
        cb_init = AsyncMock()
        cb_down = AsyncMock()
        cb_expired = AsyncMock()
        monitor.on(LifecycleEventType.INITIALIZING, cb_init)
        monitor.on(LifecycleEventType.DOWN, cb_down)
        monitor.on(LifecycleEventType.EXPIRED, cb_expired, ttl=10)
        await monitor.start()

        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.INITIALIZING))
        await asyncio.sleep(0.01)

        cb_init.assert_called_once_with("s1")
        cb_down.assert_not_called()
        cb_expired.assert_not_called()
        await monitor.stop()

    # ── READY event ────────────────────────────────────────────────────

    async def test_ready_fires_callback(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.READY, cb)
        await monitor.start()

        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.READY))
        await asyncio.sleep(0.01)

        assert "s1" in monitor._seen
        cb.assert_called_once_with("s1")
        await monitor.stop()

    # ── HEARTBEAT event ────────────────────────────────────────────────

    async def test_heartbeat_fires_callback(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.HEARTBEAT, cb)
        await monitor.start()

        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.HEARTBEAT))
        await asyncio.sleep(0.01)

        assert "s1" in monitor._seen
        cb.assert_called_once_with("s1")
        await monitor.stop()

    # ── DOWN event ─────────────────────────────────────────────────────

    async def test_down_fires_callback(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.DOWN, cb)
        await monitor.start()

        monitor._seen["s1"] = time.monotonic()
        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.DOWN))
        await asyncio.sleep(0.01)

        assert "s1" not in monitor._seen
        cb.assert_called_once_with("s1")
        await monitor.stop()

    async def test_down_removes_from_tracking(self, monitor: HealthMonitor) -> None:
        monitor.on(LifecycleEventType.DOWN, AsyncMock())
        await monitor.start()

        monitor._seen["s1"] = time.monotonic()
        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.DOWN))
        await asyncio.sleep(0.01)

        assert "s1" not in monitor._seen
        await monitor.stop()

    # ── TTL sweep (EXPIRED) ────────────────────────────────────────────

    async def test_sweep_fires_expired_callback(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.EXPIRED, cb, ttl=0.1)
        monitor._sweep_interval = 0.05
        await monitor.start()

        monitor._seen["s1"] = time.monotonic() - 10.0
        await asyncio.sleep(0.15)

        assert "s1" not in monitor._seen
        cb.assert_called_once_with("s1")
        await monitor.stop()

    async def test_sweep_does_not_fire_down_callback(self, monitor: HealthMonitor) -> None:
        cb_expired = AsyncMock()
        cb_down = AsyncMock()
        monitor.on(LifecycleEventType.EXPIRED, cb_expired, ttl=0.1)
        monitor.on(LifecycleEventType.DOWN, cb_down)
        monitor._sweep_interval = 0.05
        await monitor.start()

        monitor._seen["s1"] = time.monotonic() - 10.0
        await asyncio.sleep(0.15)

        cb_expired.assert_called_once_with("s1")
        cb_down.assert_not_called()
        await monitor.stop()

    async def test_sweep_skips_when_no_expired_registered(self, monitor: HealthMonitor) -> None:
        """Sweep is a no-op when no EXPIRED callback is registered."""
        monitor.on(LifecycleEventType.READY, AsyncMock())
        await monitor.start()

        # _ttl is None → sweep returns immediately.  No crash.
        monitor._seen["s1"] = time.monotonic() - 10.0
        await asyncio.sleep(0.05)

        assert "s1" in monitor._seen  # never swept
        await monitor.stop()

    # ── Multiple callbacks per state ───────────────────────────────────

    async def test_multiple_callbacks_per_state(self, monitor: HealthMonitor) -> None:
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        monitor.on(LifecycleEventType.DOWN, cb1)
        monitor.on(LifecycleEventType.DOWN, cb2)
        await monitor.start()

        monitor._seen["s1"] = time.monotonic()
        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.DOWN))
        await asyncio.sleep(0.01)

        cb1.assert_called_once_with("s1")
        cb2.assert_called_once_with("s1")
        await monitor.stop()

    # ── Callback error resilience ──────────────────────────────────────

    async def test_callback_exception_is_swallowed(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock(side_effect=RuntimeError("boom"))
        monitor.on(LifecycleEventType.DOWN, cb)
        await monitor.start()

        monitor._seen["s1"] = time.monotonic()
        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.DOWN))
        await asyncio.sleep(0.01)

        cb.assert_called_once_with("s1")
        await monitor.stop()

    # ── on_event returns immediately ───────────────────────────────────

    async def test_on_event_is_non_blocking(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.HEARTBEAT, cb)
        await monitor.start()

        t0 = asyncio.get_running_loop().time()
        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.HEARTBEAT))
        elapsed = asyncio.get_running_loop().time() - t0

        assert elapsed < 0.001
        await asyncio.sleep(0.01)
        cb.assert_called_once_with("s1")
        await monitor.stop()

    # ── Events before start() are ignored ──────────────────────────────

    async def test_events_ignored_before_start(self, monitor: HealthMonitor) -> None:
        cb = AsyncMock()
        monitor.on(LifecycleEventType.READY, cb)

        monitor.on_event(LifecycleEvent(service_id="s1", event=LifecycleEventType.READY))
        await asyncio.sleep(0.01)

        cb.assert_not_called()

    # ── Lifecycle: start/stop idempotency ──────────────────────────────

    async def test_double_start_is_idempotent(self, monitor: HealthMonitor) -> None:
        await monitor.start()
        task1 = monitor._sweep_task
        await monitor.start()
        assert monitor._sweep_task is task1
        await monitor.stop()

    async def test_double_stop_is_idempotent(self, monitor: HealthMonitor) -> None:
        await monitor.start()
        await monitor.stop()
        await monitor.stop()
