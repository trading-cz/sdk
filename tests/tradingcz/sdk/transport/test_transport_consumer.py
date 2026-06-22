"""Unit tests for TransportConsumer."""
# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.transport_consumer import TransportConsumer

# ── Helpers ──────────────────────────────────────────────────────────────

def _settings() -> KafkaSettings:
    return KafkaSettings(bootstrap_servers="localhost:9092", consumer_group="test-group")


def _session(**kwargs: object) -> TransportConsumer:
    with patch("tradingcz.sdk.transport.transport_consumer.AIOConsumer", autospec=True):
        s = TransportConsumer(topic="test-topic", settings=_settings(), group_suffix="test", **kwargs)  # type: ignore[arg-type]
    s._consumer = MagicMock()
    s._consumer.commit = AsyncMock()
    s._consumer.close = AsyncMock()
    s._consumer.subscribe = AsyncMock()
    s._consumer.poll = AsyncMock(return_value=None)  # poll() returns single msg or None
    s._subscribed = True
    return s


def _raw_msg(*, value: bytes = b'{"x":1}', key: bytes = b"", headers: list[tuple[str, bytes]] | None = None, offset: int = 42, partition: int = 0, topic: str = "test-topic", error: bool = False) -> MagicMock:
    msg = MagicMock()
    msg.error.return_value = error
    msg.value.return_value = value
    msg.key.return_value = key
    msg.headers.return_value = headers or []
    msg.offset.return_value = offset
    msg.partition.return_value = partition
    msg.topic.return_value = topic
    return msg


# ── Tests ────────────────────────────────────────────────────────────────

def test_build_message() -> None:
    s = _session()
    msg = s._build_message(_raw_msg(value=b"hello", key=b"k1", headers=[("h", b"v")]))
    assert msg.payload == b"hello"
    assert msg.key == "k1"
    assert msg.headers == {"h": "v"}
    assert msg.offset == 42


@pytest.mark.asyncio
async def test_handle_corrupt_calls_on_error_and_commits() -> None:
    on_error = AsyncMock()
    s = _session(on_error=on_error)
    raw = _raw_msg(error=True, partition=2, offset=99)
    raw.error.return_value = "some error"
    await s._handle_error(raw)
    on_error.assert_awaited_once_with(2, 99, "some error")
    s._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_corrupt_suppresses_callback_failure() -> None:
    s = _session(on_error=AsyncMock(side_effect=RuntimeError("boom")))
    await s._handle_error(_raw_msg(error=True))
    s._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit() -> None:
    s = _session()
    await s.commit(KafkaMessage(payload=b"x", topic="t", partition=3, offset=7))
    s._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_close() -> None:
    s = _session()
    await s.close()
    s._consumer.close.assert_awaited_once()
    await s.close()  # idempotent
    assert s._consumer.close.await_count == 1  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_poll() -> None:
    s = _session(batch_size=1)
    good = _raw_msg(value=b"ok")
    corrupt = _raw_msg(error=True)
    # poll() loop calls consumer.poll() one-by-one per message.
    # corrupt → skipped, good → collected (batch_size=1 → exit).
    s._consumer.poll = AsyncMock(side_effect=[corrupt, good])

    msgs = await s.poll()
    assert len(msgs) == 1
    assert msgs[0].payload == b"ok"


@pytest.mark.asyncio
async def test_poll_raises_when_closed() -> None:
    s = _session()
    s._closed = True
    with pytest.raises(RuntimeError, match="closed"):
        await s.poll()
