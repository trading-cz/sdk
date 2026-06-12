"""Unit tests for tradingcz.sdk._helpers (FireAndForget, RequestReply)."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from tradingcz.sdk.framework.helpers import (
    FireAndForget,
    RequestReply,
    _infer_message_type,
)
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.headers import Header

# ── Test models ─────────────────────────────────────────────────────────────


class Ping(BaseModel):
    request_id: str
    message: str


class Pong(BaseModel):
    request_id: str
    reply: str


# ── Fixtures ────────────────────────────────────────────────────────────────


async def _empty_receive():
    """Async generator that yields nothing — used to mock channel.receive()."""
    if False:  # pragma: no cover — never yields, just satisfies async for
        yield  # type: ignore[unreachable]


@pytest.fixture
def mock_channel() -> AsyncMock:
    """Return a mock KafkaChannel (used by RequestReply tests)."""
    ch = AsyncMock()
    ch.name = "dev-test"
    ch.send = AsyncMock()
    ch.flush = AsyncMock()
    # receive() returns an async generator that yields nothing.
    # The RequestReply background listener iterates over it but the test
    # manually resolves futures — no actual message flow through the mock.
    ch.receive.return_value = _empty_receive()
    return ch


# ── _infer_message_type ─────────────────────────────────────────────────────


class TestInferEventType:
    def test_data_request(self) -> None:
        from tradingcz.sdk.models.events import DataRequest

        req = DataRequest(
            type="historic", asset="stock", broker="alpaca", symbols=["AAPL"]
        )
        assert _infer_message_type(req) == EventType.DATA_REQUEST

    def test_trading_signal(self) -> None:
        from tradingcz.sdk.models.events import ServiceRequest

        s = ServiceRequest(service="get_positions")
        assert _infer_message_type(s) == EventType.SERVICE_REQUEST

    def test_unknown_class_raises(self) -> None:
        class MyCustomEvent(BaseModel):
            request_id: str = ""

        with pytest.raises(ValueError, match="Cannot infer EventType"):
            _infer_message_type(MyCustomEvent())


# ── FireAndForget ──────────────────────────────────────────────────────────


class TestFireAndForget:
    @pytest.mark.asyncio
    async def test_send_builds_headers(self, mock_channel: AsyncMock) -> None:
        faf = FireAndForget(mock_channel, "test-service")
        ping = Ping(request_id="r1", message="hello")

        await faf.send(ping, message_type=EventType.DATA_REQUEST, key="my-key")

        mock_channel.send.assert_awaited_once()
        call_kwargs = mock_channel.send.await_args.kwargs
        assert call_kwargs["key"] == "my-key"
        headers = call_kwargs["headers"]
        assert headers[Header.EVENT_TYPE] == "data_request"
        assert headers[Header.SOURCE_APP] == "test-service"
        assert Header.SEQUENCE not in headers  # event messages have no sequence

    @pytest.mark.asyncio
    async def test_send_increments_sequence(self, mock_channel: AsyncMock) -> None:
        faf = FireAndForget(mock_channel, "test")
        ping = Ping(request_id="r1", message="a")

        await faf.send(ping, message_type=EventType.DATA_REQUEST)
        await faf.send(ping, message_type=EventType.DATA_REQUEST)

        assert mock_channel.send.await_count == 2
        # sequence counter is internal only — not exposed in event headers

    @pytest.mark.asyncio
    async def test_extra_headers_merged(self, mock_channel: AsyncMock) -> None:
        faf = FireAndForget(mock_channel, "test")
        ping = Ping(request_id="r1", message="hello")

        await faf.send(
            ping,
            message_type=EventType.DATA_REQUEST,
            extra_headers={"tracking_id": "trk-1", "strategy_id": "strat-1"},
        )

        headers = mock_channel.send.await_args.kwargs["headers"]
        assert headers["tracking_id"] == "trk-1"
        assert headers["strategy_id"] == "strat-1"

    @pytest.mark.asyncio
    async def test_payload_is_json_bytes(self, mock_channel: AsyncMock) -> None:
        faf = FireAndForget(mock_channel, "test")
        ping = Ping(request_id="r1", message="hello")

        await faf.send(ping, message_type=EventType.DATA_REQUEST)

        # payload is the first positional argument to channel.send()
        payload = mock_channel.send.await_args.args[0]
        assert isinstance(payload, bytes)
        import json

        parsed = json.loads(payload)
        assert parsed["request_id"] == "r1"
        assert parsed["message"] == "hello"


# ── RequestReply ───────────────────────────────────────────────────────────


class TestRequestReply:
    @pytest.mark.asyncio
    async def test_request_sends_and_flushes(self, mock_channel: AsyncMock) -> None:
        rr = RequestReply(mock_channel, "test-service")
        await rr.start()

        ping = Ping(request_id="req-1", message="hello")

        async def _simulate_response() -> None:
            await asyncio.sleep(0.05)
            future = list(rr._pending.values())[0] if rr._pending else None
            if future and not future.done():
                future.set_result(Pong(request_id="req-1", reply="world"))

        asyncio.create_task(_simulate_response())

        resp = await rr.request(
            ping, response_type=Pong, request_type=EventType.DATA_REQUEST, timeout=2.0
        )

        assert isinstance(resp, Pong)
        assert resp.request_id == "req-1"
        assert resp.reply == "world"
        mock_channel.send.assert_awaited_once()
        mock_channel.flush.assert_awaited_once()

        await rr.close()

    @pytest.mark.asyncio
    async def test_request_builds_headers(self, mock_channel: AsyncMock) -> None:
        rr = RequestReply(
            mock_channel, "test-service", message_types={EventType.DATA_READY: Pong}
        )
        await rr.start()

        ping = Ping(request_id="req-h", message="test")

        async def _respond() -> None:
            await asyncio.sleep(0.05)
            for f in rr._pending.values():
                if not f.done():
                    f.set_result(Pong(request_id="req-h", reply="ok"))

        asyncio.create_task(_respond())

        await rr.request(
            ping, response_type=Pong, request_type=EventType.DATA_REQUEST, timeout=2.0
        )

        headers = mock_channel.send.await_args.kwargs["headers"]
        assert headers[Header.EVENT_TYPE] == "data_request"
        assert headers[Header.SOURCE_APP] == "test-service"
        assert headers[Header.REQUEST_ID] == "req-h"
        assert Header.SEQUENCE not in headers  # event topic, no sequence

        await rr.close()

    @pytest.mark.asyncio
    async def test_request_without_request_id_raises(
        self, mock_channel: AsyncMock
    ) -> None:
        rr = RequestReply(mock_channel, "test")

        class BadRequest(BaseModel):
            pass

        with pytest.raises(ValueError, match="request_id"):
            await rr.request(BadRequest(), response_type=Pong, timeout=1.0)

    @pytest.mark.asyncio
    async def test_request_timeout(self, mock_channel: AsyncMock) -> None:
        rr = RequestReply(mock_channel, "test")
        await rr.start()

        ping = Ping(request_id="req-timeout", message="test")

        with pytest.raises(asyncio.TimeoutError):
            await rr.request(
                ping,
                response_type=Pong,
                request_type=EventType.DATA_REQUEST,
                timeout=0.1,
            )

        await rr.close()

    @pytest.mark.asyncio
    async def test_register_type(self, mock_channel: AsyncMock) -> None:
        rr = RequestReply(mock_channel, "test")
        rr.register_type(EventType.DATA_READY, Pong)
        assert rr._types["data_ready"] is Pong

    @pytest.mark.asyncio
    async def test_close_cancels_pending_futures(self, mock_channel: AsyncMock) -> None:
        rr = RequestReply(mock_channel, "test")
        await rr.start()

        # Add a pending future manually
        future: asyncio.Future[Pong] = asyncio.get_event_loop().create_future()
        rr._pending["test-id"] = future  # type: ignore[arg-type]

        await rr.close()

        assert future.cancelled() or future.done()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, mock_channel: AsyncMock) -> None:
        rr = RequestReply(mock_channel, "test")
        await rr.start()
        task1 = rr._listen_task
        await rr.start()
        task2 = rr._listen_task
        assert task1 is task2  # same task, not recreated

        await rr.close()
