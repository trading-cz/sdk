"""Unit tests for TradingApp — lifecycle, health integration, feature flags."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fake_kafka import FakeKafkaTransport
from tradingcz.sdk._app import TradingApp


@pytest.fixture
def fake_transport() -> None:
    """Replace KafkaTransport with FakeKafkaTransport (in-memory mockafka-py).

    HealthPublisher is also mocked by default — individual tests can
    override the mock to track call order when needed.
    """
    with (
        patch("tradingcz.sdk._service.KafkaTransport", FakeKafkaTransport),
        patch("tradingcz.sdk._service.HealthPublisher") as mock_hp_cls,
    ):
        mock_hp = MagicMock()
        mock_hp.start = AsyncMock()
        mock_hp.close = AsyncMock()
        mock_hp_cls.return_value = mock_hp
        yield mock_hp


class TestTradingAppLifecycle:
    """Tests for TradingApp start/close/context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self, fake_transport: MagicMock) -> None:
        async with TradingApp(service_id="test-app", health_interval=300) as app:
            assert app.stock is not None
            assert app.options is not None
            assert app.corporate_actions is not None
            assert app.signals is not None
            assert app.positions is not None
            assert app.balance is not None
            assert app.orders is not None

    @pytest.mark.asyncio
    async def test_feature_flags_disable_clients(self, fake_transport: MagicMock) -> None:
        app = TradingApp(service_id="test-app")
        app.with_stock(False).with_options(False).with_corporate_actions(False)
        app.with_signals(False).with_positions(False)
        app.with_balance(False).with_orders(False)

        await app.start()

        assert app.stock is None
        assert app.options is None
        assert app.corporate_actions is None
        assert app.signals is None
        assert app.positions is None
        assert app.balance is None
        assert app.orders is None

        await app.close()

    @pytest.mark.asyncio
    async def test_env_vars_respected(self, fake_transport: MagicMock) -> None:
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
    async def test_explicit_params_override_env(self, fake_transport: MagicMock) -> None:
        os.environ["SDK_ENV"] = "prod"

        app = TradingApp(service_id="test-app", env="staging")
        assert app._env == "staging"  # explicit beats env

        del os.environ["SDK_ENV"]

    @pytest.mark.asyncio
    async def test_health_emits_up_on_start(self, fake_transport: MagicMock) -> None:
        """Verify HealthPublisher.start() is called during TradingApp.start()."""
        # fake_transport already patches HealthPublisher — grab the mock
        mock_hp = fake_transport
        assert isinstance(mock_hp, MagicMock)

        app = TradingApp(service_id="test-app", health_interval=120)
        await app.start()

        # start() was called → emits "up"
        mock_hp.start.assert_awaited_once()

        await app.close()

        # close() was called → emits "down"
        mock_hp.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_order_health_before_transport(self, fake_transport: MagicMock) -> None:
        """Health must close BEFORE transport (so 'down' event can be sent)."""
        # Override the HealthPublisher mock with one that tracks call order
        with patch("tradingcz.sdk._service.HealthPublisher") as mock_hp_cls:
            mock_hp = MagicMock()
            mock_hp.start = AsyncMock()
            mock_hp.close = AsyncMock()
            mock_hp_cls.return_value = mock_hp

            # Track call order
            call_order = []

            async def _tracking_health_close() -> None:
                call_order.append("health_closed")

            mock_hp.close.side_effect = _tracking_health_close

            # Wrap FakeKafkaTransport.close to track call order
            original_close = FakeKafkaTransport.close

            async def _tracking_transport_close(self: FakeKafkaTransport) -> None:
                await original_close(self)
                call_order.append("transport_closed")

            with patch.object(FakeKafkaTransport, "close", _tracking_transport_close):
                app = TradingApp(service_id="test-app")
                await app.start()
                await app.close()

            # Health must close before transport
            assert call_order == ["health_closed", "transport_closed"], (
                f"Expected health before transport, got {call_order}"
            )
