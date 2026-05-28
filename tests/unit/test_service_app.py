"""Unit tests for ServiceApp — base class for all services."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingcz.sdk._service import ServiceApp


@pytest.fixture
def fake_transport() -> MagicMock:
    """Mock KafkaTransport + HealthPublisher so start() doesn't connect to real Kafka."""
    with (
        patch("tradingcz.sdk._service.KafkaTransport") as mock_transport_cls,
        patch("tradingcz.sdk._service.HealthPublisher") as mock_hp_cls,
    ):
        transport = MagicMock()
        transport.channel = AsyncMock(return_value=AsyncMock())
        transport.close = AsyncMock()
        mock_transport_cls.return_value = transport

        mock_hp = MagicMock()
        mock_hp.start = AsyncMock()
        mock_hp.close = AsyncMock()
        mock_hp_cls.return_value = mock_hp
        yield transport


class TestServiceApp:
    """Tests for ServiceApp base class."""

    @pytest.mark.asyncio
    async def test_start_sets_transport_and_topics(self, fake_transport: MagicMock) -> None:
        svc = ServiceApp(service_id="test-svc")
        await svc.start()

        assert svc.transport is not None
        assert svc.topics is not None
        assert svc.events_channel is not None
        assert svc.service_id == "test-svc"
        assert svc.source_app == "test-svc"

        await svc.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, fake_transport: MagicMock) -> None:
        async with ServiceApp(service_id="test-svc") as svc:
            assert svc.transport is not None

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, fake_transport: MagicMock) -> None:
        svc = ServiceApp(service_id="test-svc")
        await svc.start()
        await svc.close()

        fake_transport.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_env_vars_respected(self, fake_transport: MagicMock) -> None:
        os.environ["SDK_ENV"] = "prod"
        os.environ["SDK_HEALTH_INTERVAL"] = "120"

        svc = ServiceApp(service_id="test-svc")
        assert svc._env == "prod"
        assert svc._health_interval == 120.0

        del os.environ["SDK_ENV"]
        del os.environ["SDK_HEALTH_INTERVAL"]

    @pytest.mark.asyncio
    async def test_shutdown_event(self, fake_transport: MagicMock) -> None:
        svc = ServiceApp(service_id="test-svc")
        await svc.start()

        svc.request_shutdown()
        await asyncio.wait_for(svc.wait_for_shutdown(), timeout=0.5)

        await svc.close()
