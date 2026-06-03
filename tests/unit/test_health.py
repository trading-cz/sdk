"""Unit tests for tradingcz.sdk._health.HealthPublisher."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tradingcz.models.health import ServiceLifecycle
from tradingcz.framework.health import HealthPublisher


@pytest.fixture
def mock_faf() -> AsyncMock:
    """Mock FireAndForget."""
    faf = AsyncMock()
    faf.send = AsyncMock()
    return faf


class TestHealthPublisher:
    """Tests for HealthPublisher lifecycle events."""

    @pytest.mark.asyncio
    async def test_start_emits_up(self, mock_faf: AsyncMock) -> None:
        hp = HealthPublisher(mock_faf, "test-service", interval=300)
        await hp.start()

        # Should have sent "up" event
        mock_faf.send.assert_awaited_once()
        call_args = mock_faf.send.await_args
        lifecycle: ServiceLifecycle = call_args.args[0]
        assert isinstance(lifecycle, ServiceLifecycle)
        assert lifecycle.service_id == "test-service"
        assert lifecycle.event == "up"

        await hp.close()

    @pytest.mark.asyncio
    async def test_close_emits_down(self, mock_faf: AsyncMock) -> None:
        hp = HealthPublisher(mock_faf, "test-service", interval=300)
        await hp.start()
        mock_faf.send.reset_mock()

        await hp.close()

        # Should have sent "down" — event may be after heartbeat
        down_calls = [c for c in mock_faf.send.await_args_list if c.args[0].event == "down"]
        assert len(down_calls) == 1

    @pytest.mark.asyncio
    async def test_heartbeat_emitted(self, mock_faf: AsyncMock) -> None:
        """Heartbeat fires after interval. We patch asyncio.sleep to
        speed up the test while still yielding control."""
        hp = HealthPublisher(mock_faf, "test-service", interval=60.0)
        await hp.start()
        mock_faf.send.reset_mock()

        # Replace the internal interval with 0 so the loop body runs
        # after each yield, but still use real asyncio.sleep(0) to yield.
        hp._interval = 0

        # Yield control several times so the heartbeat task body runs
        for _ in range(5):
            await asyncio.sleep(0)

        await hp.close()

        heartbeat_calls = [
            c for c in mock_faf.send.await_args_list if c.args[0].event == "heartbeat"
        ]
        assert len(heartbeat_calls) >= 1, (
            f"Expected >=1 heartbeat, got {len(heartbeat_calls)}. "
            f"All calls: {[c.args[0].event for c in mock_faf.send.await_args_list]}"
        )

    @pytest.mark.asyncio
    async def test_start_idempotent(self, mock_faf: AsyncMock) -> None:
        hp = HealthPublisher(mock_faf, "test-service", interval=300)
        await hp.start()
        mock_faf.send.reset_mock()
        await hp.start()  # second start — no-op

        # Should NOT emit a second "up"
        up_calls = [c for c in mock_faf.send.await_args_list if c.args[0].event == "up"]
        assert len(up_calls) == 0

        await hp.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, mock_faf: AsyncMock) -> None:
        hp = HealthPublisher(mock_faf, "test-service", interval=300)
        await hp.start()
        await hp.close()
        mock_faf.send.reset_mock()
        await hp.close()  # second close — no-op

        # Should NOT emit a second "down"
        down_calls = [c for c in mock_faf.send.await_args_list if c.args[0].event == "down"]
        assert len(down_calls) == 0

    @pytest.mark.asyncio
    async def test_message_type_header(self, mock_faf: AsyncMock) -> None:
        hp = HealthPublisher(mock_faf, "test-service", interval=300)
        await hp.start()

        call_args = mock_faf.send.await_args
        assert call_args.kwargs["message_type"] == "service_lifecycle"
        assert call_args.kwargs["key"] == "service_lifecycle:test-service:up"

        extra = call_args.kwargs.get("extra_headers", {})
        assert extra.get("lifecycle_event") == "up"

        await hp.close()

    @pytest.mark.asyncio
    async def test_minimum_interval_enforced(self, mock_faf: AsyncMock) -> None:
        hp = HealthPublisher(mock_faf, "test-service", interval=0.1)
        assert hp._interval == 1.0  # clamped to minimum 1s

    @pytest.mark.asyncio
    async def test_interval_from_env(self, mock_faf: AsyncMock) -> None:
        import os

        os.environ["SDK_HEALTH_INTERVAL"] = "60"
        hp = HealthPublisher(mock_faf, "test-service", interval=300)
        # The env var is read by TradingApp.__init__, not HealthPublisher.
        # HealthPublisher just uses whatever interval it's given.
        assert hp._interval == 300.0  # uses constructor value
        del os.environ["SDK_HEALTH_INTERVAL"]

    @pytest.mark.asyncio
    async def test_emit_failure_does_not_crash(self, mock_faf: AsyncMock) -> None:
        mock_faf.send.side_effect = RuntimeError("kafka down")
        hp = HealthPublisher(mock_faf, "test-service", interval=300)

        # Should not raise — emits are best-effort
        await hp.start()
        # start() still completed (failure logged, not raised)
        assert hp._running
        await hp.close()
