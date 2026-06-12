"""Unit tests for HealthMonitor."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from tradingcz.sdk.framework.health import HealthMonitor
from tradingcz.sdk.models.health import ServiceLifecycle


class TestHealthMonitor:
    """Tests for HealthMonitor — liveness tracking via ServiceLifecycle events."""

    @pytest.fixture
    def channel(self) -> MagicMock:
        ch = MagicMock()
        ch.name = "dev-event"
        return ch

    @pytest.fixture
    def monitor(self, channel: MagicMock) -> HealthMonitor:
        return HealthMonitor(channel, ttl=600, sweep_interval=60)

    def test_init_defaults(self, channel: MagicMock) -> None:
        m = HealthMonitor(channel)
        assert m._ttl == 600
        assert m._sweep_interval == 60

    def test_init_custom(self, channel: MagicMock) -> None:
        m = HealthMonitor(channel, ttl=300, sweep_interval=30)
        assert m._ttl == 300
        assert m._sweep_interval == 30

    def test_on_down_registers_callback(self, monitor: HealthMonitor) -> None:
        called: list[str] = []

        async def cb(sid: str) -> None:
            called.append(sid)

        monitor.on_down(cb)
        assert monitor._on_down is cb

    @pytest.mark.asyncio
    async def test_notify_calls_callback(self, monitor: HealthMonitor) -> None:
        called: list[str] = []

        async def cb(sid: str) -> None:
            called.append(sid)

        monitor.on_down(cb)
        await monitor._notify("strat-1")
        assert called == ["strat-1"]

    @pytest.mark.asyncio
    async def test_notify_no_callback_is_safe(self, monitor: HealthMonitor) -> None:
        """_notify with no callback registered should not raise."""
        await monitor._notify("strat-1")  # does nothing, doesn't crash

    @pytest.mark.asyncio
    async def test_notify_callback_exception_does_not_propagate(
        self, monitor: HealthMonitor
    ) -> None:
        async def bad_cb(sid: str) -> None:
            raise RuntimeError("boom")

        monitor.on_down(bad_cb)
        # Should not raise
        await monitor._notify("strat-1")

    @pytest.mark.asyncio
    async def test_consume_tracks_up_and_heartbeat(
        self, channel: MagicMock, monitor: HealthMonitor
    ) -> None:
        """_consume should update _seen on up/heartbeat, notify on down."""
        events: list[MagicMock] = []

        for sid, evt in [("strat-1", "up"), ("strat-1", "heartbeat")]:
            msg = MagicMock()
            msg.headers = {"event_type": "service_lifecycle"}
            msg.payload = ServiceLifecycle(service_id=sid, event=evt).model_dump_json().encode()  # type: ignore[arg-type]
            events.append(msg)

        # Simulate receive() yielding events then stopping
        async def _receive(
            *, group_suffix: str = "", idle_timeout: float = 0.0
        ) -> object:
            for e in events:
                yield e
            # After yielding, block forever (simulating continuous consume)

        channel.receive = MagicMock(
            side_effect=[
                _receive(),
            ]
        )

        # Run _consume briefly
        monitor._running = True
        task = asyncio.create_task(monitor._consume())
        await asyncio.sleep(0.05)
        monitor._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert "strat-1" in monitor._seen

    @pytest.mark.asyncio
    async def test_consume_triggers_notify_on_down(
        self, channel: MagicMock, monitor: HealthMonitor
    ) -> None:
        """_consume should call on_down when a 'down' event arrives."""
        called: list[str] = []

        async def cb(sid: str) -> None:
            called.append(sid)

        monitor.on_down(cb)

        msg = MagicMock()
        msg.headers = {"event_type": "service_lifecycle"}
        msg.payload = ServiceLifecycle(service_id="strat-1", event="down").model_dump_json().encode()  # type: ignore[arg-type]

        async def _receive(
            *, group_suffix: str = "", idle_timeout: float = 0.0
        ) -> object:
            yield msg

        channel.receive = MagicMock(side_effect=[_receive()])

        monitor._running = True
        task = asyncio.create_task(monitor._consume())
        await asyncio.sleep(0.05)
        monitor._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert called == ["strat-1"]
        assert "strat-1" not in monitor._seen

    @pytest.mark.asyncio
    async def test_sweep_detects_timeout(self, monitor: HealthMonitor) -> None:
        """Sweep should fire on_down for services past TTL."""
        called: list[str] = []

        async def cb(sid: str) -> None:
            called.append(sid)

        monitor.on_down(cb)

        # Inject a stale entry
        monitor._seen["stale-app"] = time.monotonic() - 999
        monitor._ttl = 0.01  # very short TTL

        # Run one sweep iteration manually
        now = time.monotonic()
        for service_id, last_seen in list(monitor._seen.items()):
            if now - last_seen > monitor._ttl:
                del monitor._seen[service_id]
                await monitor._notify(service_id)

        assert "stale-app" in called
        assert "stale-app" not in monitor._seen

    @pytest.mark.asyncio
    async def test_start_stop_idempotent(self, monitor: HealthMonitor) -> None:
        await monitor.start()
        assert monitor._running is True
        await monitor.start()  # no-op
        assert monitor._running is True
        await monitor.stop()
        assert monitor._running is False
        await monitor.stop()  # no-op
        assert monitor._running is False
