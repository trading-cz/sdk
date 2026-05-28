"""Unit tests for ServiceApp — base class for all services."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tradingcz.sdk._service import ServiceApp


@pytest.fixture
def mock_transport() -> MagicMock:
    """Patch KafkaTransport so start() doesn't connect to real Kafka."""
    with patch("tradingcz.sdk._service.KafkaTransport") as mock_cls:
        transport = MagicMock()
        transport.channel = AsyncMock(return_value=AsyncMock())
        transport.close = AsyncMock()
        mock_cls.return_value = transport
        yield transport


class TestServiceApp:
    """Tests for ServiceApp base class."""

    @pytest.mark.asyncio
    async def test_start_sets_transport_and_topics(self, mock_transport: MagicMock) -> None:
        svc = ServiceApp(service_id="test-svc")
        await svc.start()

        assert svc.transport is not None
        assert svc.topics is not None
        assert svc.events_channel is not None
        assert svc.service_id == "test-svc"

        await svc.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_transport: MagicMock) -> None:
        async with ServiceApp(service_id="test-svc") as svc:
            assert svc.transport is not None

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, mock_transport: MagicMock) -> None:
        svc = ServiceApp(service_id="test-svc")
        await svc.start()
        await svc.close()

        mock_transport.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_env_vars_respected(self, mock_transport: MagicMock) -> None:
        import os
        os.environ["SDK_ENV"] = "prod"
        os.environ["SDK_HEALTH_INTERVAL"] = "120"

        svc = ServiceApp(service_id="test-svc")
        assert svc._env == "prod"
        assert svc._health_interval == 120.0

        del os.environ["SDK_ENV"]
        del os.environ["SDK_HEALTH_INTERVAL"]

    @pytest.mark.asyncio
    async def test_shutdown_event(self, mock_transport: MagicMock) -> None:
        import asyncio

        svc = ServiceApp(service_id="test-svc")
        await svc.start()

        # request_shutdown should set the event
        svc.request_shutdown()

        # wait_for_shutdown should return immediately
        await asyncio.wait_for(svc.wait_for_shutdown(), timeout=0.5)

        await svc.close()
