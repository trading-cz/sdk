"""Unit tests for _DataTransport historical reads and stream filtering."""
# pylint: disable=protected-access

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tradingcz.sdk.exceptions import DataError, TransportTimeoutError
from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.models.enums.event import (
    AssetType,
    Broker,
    DataRequestType,
    EventType,
    MarketDataType,
)
from tradingcz.sdk.models.events import DataError as DataErrorReply
from tradingcz.sdk.models.events import DataReady
from tradingcz.sdk.models.market import Bar
from tradingcz.sdk.transport.kafka_header import DataHeader
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicRegistry

_CONSUMER = "tradingcz.sdk.market_data._internal._transport.TransportConsumer"


class _FakeConsumer:
    """Single-partition topic: serves the records in one batch, then idles like a caught-up consumer."""

    def __init__(self, records: Callable[[], list[KafkaMessage]], *, unread: int = 0) -> None:
        self._records = records
        self._unread = unread  # records stored after the served ones that the consumer has not reached yet
        self._served = False
        self.close = AsyncMock()

    def _stored(self) -> list[KafkaMessage]:
        return [replace(msg, partition=0, offset=offset) for offset, msg in enumerate(self._records())]

    async def watermarks(self) -> dict[int, tuple[int, int]]:
        return {0: (0, len(self._records()) + self._unread)}

    async def poll(self) -> list[KafkaMessage]:
        if self._served:
            await asyncio.sleep(0.01)
            return []
        self._served = True
        return self._stored()

    async def __aiter__(self) -> AsyncIterator[KafkaMessage]:
        for msg in self._stored():
            yield msg
        await asyncio.Event().wait()


def _bar(symbol: str, day: int) -> Bar:
    return Bar(symbol=symbol, timestamp=datetime(2026, 1, day, tzinfo=UTC), open=1, high=1, low=1, close=1, volume=1)


def _record(bar: Bar, event_id: str, sequence: int | None = None) -> KafkaMessage:
    """A data record with the headers ingestion produces."""
    headers = DataHeader(event_type=EventType.BAR, source_app="ingestion", event_id=event_id, symbol=bar.symbol, sequence=sequence)
    return KafkaMessage(payload=bar.model_dump_json().encode(), key=bar.symbol, headers=headers.to_headers())


def _event_id(request: AsyncMock) -> str:
    return request.await_args.kwargs["event_id"]


def _transport(ready: DataReady) -> tuple[_DataTransport, AsyncMock]:
    rr = MagicMock()
    rr.request = AsyncMock(return_value=ready)
    transport = _DataTransport(rr=rr, producer=MagicMock(), settings=KafkaSettings(consumer_group="g"), topics=KafkaTopicRegistry("tst"), service_id="svc")
    transport._topic_admin.ensure = AsyncMock()  # type: ignore[method-assign]
    return transport, rr.request


def _historic(record_count: int) -> DataReady:
    return DataReady(broker=Broker.ALPACA, data_topic="tst-stock-historical", record_count=record_count)


@pytest.mark.asyncio
async def test_historical_returns_every_record_of_the_request() -> None:
    transport, request = _transport(_historic(3))

    def records() -> list[KafkaMessage]:
        event_id = _event_id(request)
        return [
            _record(_bar("AAPL", 2), event_id, 1),
            _record(_bar("AAPL", 9), str(uuid4()), 0),  # another app's request on the shared topic
            _record(_bar("AAPL", 1), event_id, 0),
            _record(_bar("MSFT", 1), event_id, 2),
        ]

    consumer = _FakeConsumer(records)
    with patch(_CONSUMER, return_value=consumer):
        result = await transport.request_historical(["AAPL", "MSFT"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=1)

    assert {symbol: [bar.timestamp.day for bar in bars] for symbol, bars in result.items()} == {"AAPL": [1, 2], "MSFT": [1]}
    consumer.close.assert_awaited()


@pytest.mark.asyncio
async def test_historical_drops_duplicate_records() -> None:
    transport, request = _transport(_historic(2))
    consumer = _FakeConsumer(lambda: [_record(_bar("AAPL", day), _event_id(request), seq) for day, seq in ((1, 0), (1, 0), (2, 1))])
    with patch(_CONSUMER, return_value=consumer):
        result = await transport.request_historical(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=1)

    assert [bar.timestamp.day for bar in result["AAPL"]] == [1, 2]


@pytest.mark.asyncio
async def test_historical_counts_records_without_sequence() -> None:
    transport, request = _transport(_historic(2))
    consumer = _FakeConsumer(lambda: [_record(_bar("AAPL", day), _event_id(request)) for day in (1, 2)])
    with patch(_CONSUMER, return_value=consumer):
        result = await transport.request_historical(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=1)

    assert [bar.timestamp.day for bar in result["AAPL"]] == [1, 2]


@pytest.mark.asyncio
async def test_historical_without_records_returns_immediately() -> None:
    transport, _ = _transport(_historic(0))
    with patch(_CONSUMER) as consumer_cls:
        assert await transport.request_historical(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=1) == {}
    consumer_cls.assert_not_called()


@pytest.mark.asyncio
async def test_historical_names_lost_records_without_waiting_for_the_timeout() -> None:
    transport, request = _transport(_historic(3))
    consumer = _FakeConsumer(lambda: [_record(_bar("AAPL", day), _event_id(request), seq) for day, seq in ((1, 0), (3, 2))])
    with patch(_CONSUMER, return_value=consumer), pytest.raises(DataError, match=r"1 missing \(seq 1\)"):
        async with asyncio.timeout(1):
            await transport.request_historical(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=30)
    consumer.close.assert_awaited()


@pytest.mark.asyncio
async def test_historical_times_out_while_records_are_still_unread() -> None:
    transport, request = _transport(_historic(2))
    consumer = _FakeConsumer(lambda: [_record(_bar("AAPL", 1), _event_id(request), 0)], unread=5)
    with patch(_CONSUMER, return_value=consumer), pytest.raises(TransportTimeoutError, match=r"1/2 records .* \(seq 1\)"):
        await transport.request_historical(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=0.05)
    consumer.close.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (DataErrorReply(broker=Broker.ALPACA, error="symbol not found"), "symbol not found"),
        (DataReady(broker=Broker.ALPACA, data_topic="t", type=DataRequestType.STREAM), "Expected historic DataReady"),
    ],
)
async def test_historical_raises_data_error_for_error_or_unexpected_reply(reply: DataReady | DataErrorReply, message: str) -> None:
    transport, _ = _transport(reply)  # type: ignore[arg-type]
    with patch(_CONSUMER) as consumer_cls, pytest.raises(DataError, match=message):
        await transport.request_historical(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=1)
    consumer_cls.assert_not_called()


@pytest.mark.asyncio
async def test_stream_yields_only_requested_symbols() -> None:
    ready = DataReady(broker=Broker.ALPACA, data_topic="tst-stock-stream-bars", type=DataRequestType.STREAM)
    transport, _ = _transport(ready)
    consumer = _FakeConsumer(lambda: [_record(_bar(symbol, 1), "") for symbol in ("MSFT", "AAPL", "TSLA", "AAPL")])
    with patch(_CONSUMER, return_value=consumer):
        handle = await transport.stream(["AAPL"], AssetType.STOCK, MarketDataType.BARS, Bar, timeout=1)
        received = [await anext(handle), await anext(handle)]
        await handle._iterator.aclose()  # type: ignore[attr-defined]

    assert [bar.symbol for bar in received] == ["AAPL", "AAPL"]
    consumer.close.assert_awaited()
