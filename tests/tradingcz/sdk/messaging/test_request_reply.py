"""Unit tests for RequestReply."""
# pylint: disable=protected-access

import asyncio
from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingcz.sdk.exceptions import ServiceNotReadyError, TransportError
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import DataRequestType
from tradingcz.sdk.models.events import DataReady, DataRequest
from tradingcz.sdk.transport.kafka_settings import KafkaSettings


def _running_rr() -> RequestReply:
    """A RequestReply whose listener counts as running; replies are resolved by the test."""
    rr = RequestReply(MagicMock(), KafkaSettings(consumer_group="t"), "svc", "rr", response_types=[DataReady])
    rr._listen_task = MagicMock(done=MagicMock(return_value=False))
    rr._typed_producer.send = AsyncMock()
    rr._typed_producer.flush = AsyncMock()
    return rr


@pytest.mark.asyncio
async def test_reply_arriving_during_send_is_not_lost() -> None:
    rr = _running_rr()
    rr._typed_producer.send = AsyncMock(side_effect=lambda _req, key, headers: rr._pending[headers.event_id].set_result("reply"))

    request = DataRequest(type=DataRequestType.HISTORIC, symbols=["SPY"])
    assert await rr.request(request, response_type=DataReady, timeout=1) == "reply"


@pytest.mark.asyncio
async def test_concurrent_requests_correlate_by_their_own_event_id() -> None:
    rr = _running_rr()
    request = DataRequest(type=DataRequestType.HISTORIC, symbols=["SPY"])  # the same payload twice: the ID belongs to the call
    first = asyncio.create_task(rr.request(request, response_type=DataReady, event_id="first", timeout=1))
    second = asyncio.create_task(rr.request(request, response_type=DataReady, timeout=1))
    await asyncio.sleep(0)

    first_id, second_id = (call.kwargs["headers"].event_id for call in rr._typed_producer.send.await_args_list)
    assert first_id == "first"
    assert second_id not in ("", "first")
    rr._pending[second_id].set_result("B")
    assert await second == "B"
    rr._pending["first"].set_result("A")  # second's cleanup must not drop first's future
    assert await first == "A"


@pytest.mark.asyncio
async def test_request_fails_fast_when_listener_is_not_running() -> None:
    rr = RequestReply(MagicMock(), KafkaSettings(consumer_group="t"), "svc", "rr", response_types=[DataReady])
    with pytest.raises(ServiceNotReadyError):
        await rr.request(DataRequest(type=DataRequestType.HISTORIC, symbols=["SPY"]), response_type=DataReady, timeout=30)


@pytest.mark.asyncio
async def test_listener_crash_fails_pending_requests_and_start_restarts_it() -> None:
    sent = asyncio.Event()

    class _CrashingConsumer:
        """Fails like a lost broker once the request has been sent."""

        def __aiter__(self) -> Self:
            return self

        async def __anext__(self) -> None:
            await sent.wait()
            raise RuntimeError("broker gone")

    rr = RequestReply(MagicMock(), KafkaSettings(consumer_group="t"), "svc", "rr", response_types=[DataReady])
    rr._typed_producer.send = AsyncMock(side_effect=lambda *_args, **_kwargs: sent.set())
    rr._typed_producer.flush = AsyncMock()

    with patch("tradingcz.sdk.messaging.request_reply.TypedConsumer", return_value=_CrashingConsumer()):
        await rr.start()
        with pytest.raises(TransportError, match="listener crashed"):
            async with asyncio.timeout(1):
                await rr.request(DataRequest(type=DataRequestType.HISTORIC, symbols=["SPY"]), response_type=DataReady, timeout=30)

        crashed = rr._listen_task
        await rr.start()
        assert rr._listen_task is not crashed
        await rr.close()
