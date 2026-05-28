"""Unit tests for TradingApp — lifecycle, health integration, feature flags."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tradingcz.sdk._app import TradingApp


@pytest.fixture
def mock_transport() -> MagicMock:
    """Patch KafkaTransport so TradingApp.start() doesn't connect to real Kafka."""
    with patch("tradingcz.sdk._app.KafkaTransport") as mock_cls:
        transport = MagicMock()
        transport.channel = AsyncMock(return_value=AsyncMock())
        transport.close = AsyncMock()
        mock_cls.return_value = transport
        yield transport


class TestTradingAppLifecycle:
    """Tests for TradingApp start/close/context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_transport: MagicMock) -> None:
        async with TradingApp(service_id="test-app", health_interval=300) as app:
            assert app.data is not None
            assert app.signals is not None
            assert app.positions is not None
            assert app.balance is not None
            assert app.orders is not None

        # After exit, transport should be closed
        mock_transport.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_feature_flags_disable_clients(self, mock_transport: MagicMock) -> None:
        app = TradingApp(service_id="test-app")
        app.with_data(False).with_signals(False).with_positions(False)
        app.with_balance(False).with_orders(False)

        await app.start()

        assert app.data is None
        assert app.signals is None
        assert app.positions is None
        assert app.balance is None
        assert app.orders is None

        await app.close()

    @pytest.mark.asyncio
    async def test_env_vars_respected(self, mock_transport: MagicMock) -> None:
        os.environ["SDK_ENV"] = "prod"
        os.environ["SDK_BROKER"] = "ibkr"
        os.environ["SDK_HEALTH_INTERVAL"] = "120"

        app = TradingApp(service_id="test-app")
        assert app._env == "prod"
        assert app._broker == "ibkr"
        assert app._health_interval == 120.0

        del os.environ["SDK_ENV"]
        del os.environ["SDK_BROKER"]
        del os.environ["SDK_HEALTH_INTERVAL"]

    @pytest.mark.asyncio
    async def test_explicit_params_override_env(self, mock_transport: MagicMock) -> None:
        os.environ["SDK_ENV"] = "prod"

        app = TradingApp(service_id="test-app", env="staging")
        assert app._env == "staging"  # explicit beats env

        del os.environ["SDK_ENV"]

    @pytest.mark.asyncio
    async def test_health_emits_up_on_start(self, mock_transport: MagicMock) -> None:
        """Verify HealthPublisher.start() is called during TradingApp.start()."""
        with patch("tradingcz.sdk._app.HealthPublisher") as mock_hp_cls:
            mock_hp = MagicMock()
            mock_hp.start = AsyncMock()
            mock_hp.close = AsyncMock()
            mock_hp_cls.return_value = mock_hp

            app = TradingApp(service_id="test-app", health_interval=120)
            await app.start()

            # HealthPublisher was created with correct params
            mock_hp_cls.assert_called_once()
            call_args = mock_hp_cls.call_args
            # HealthPublisher(faf, service_id, interval=...)
            # service_id is positional arg #2 (index 1)
            assert call_args.args[1] == "test-app"
            assert call_args.kwargs["interval"] == 120.0

            # start() was called → emits "up"
            mock_hp.start.assert_awaited_once()

            await app.close()

            # close() was called → emits "down"
            mock_hp.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_order_health_before_transport(self, mock_transport: MagicMock) -> None:
        """Health must close BEFORE transport (so 'down' event can be sent)."""
        with patch("tradingcz.sdk._app.HealthPublisher") as mock_hp_cls:
            mock_hp = MagicMock()
            mock_hp.start = AsyncMock()
            mock_hp.close = AsyncMock()
            mock_hp_cls.return_value = mock_hp

            # Track call order
            call_order = []

            async def _tracking_close() -> None:
                call_order.append("health_closed")
            mock_hp.close.side_effect = _tracking_close

            async def _tracking_transport_close() -> None:
                call_order.append("transport_closed")
            mock_transport.close.side_effect = _tracking_transport_close

            app = TradingApp(service_id="test-app")
            await app.start()
            await app.close()

            # Health must close before transport
            assert call_order == ["health_closed", "transport_closed"], (
                f"Expected health before transport, got {call_order}"
            )
