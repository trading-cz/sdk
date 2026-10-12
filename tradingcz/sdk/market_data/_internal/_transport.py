"""Internal transport layer — request/reply + typed consumption.

Application code never references this module directly.
"""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from tradingcz.sdk import exceptions
from tradingcz.sdk.market_data._internal._stream_handle import StreamHandle, _Unsubscribe
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import (
    AssetType,
    Broker,
    DataRequestType,
    MarketDataType,
)
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.events import DataError, DataReady, DataRequest
from tradingcz.sdk.transport.kafka_header import Header
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.transport.transport_consumer import TransportConsumer
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


def _missing(received: set[int], expected: int) -> str:
    """Name the sequence numbers not received yet, e.g. ``2 missing (seq 57, 98)``."""
    missing = sorted(set(range(expected)) - received)
    shown = ", ".join(str(seq) for seq in missing[:10])
    return f"{len(missing)} missing (seq {shown}{', ...' if len(missing) > 10 else ''})"


class _DataTransport:
    """Internal: shared request/reply + typed consumption for market data clients.

    One ``_DataTransport`` is created per broker scope and shared by all
    data clients that use the same broker.
    """

    def __init__(
        self,
        rr: RequestReply,
        producer: TransportProducer,
        settings: KafkaSettings,
        topics: KafkaTopicRegistry,
        service_id: str,
        broker: Broker = Broker.ALPACA,
    ) -> None:
        self._rr = rr
        self._producer = producer
        self._settings = settings
        self._topics = topics
        self._service_id = service_id
        self._broker = broker
        self._topic_admin = KafkaTopicAdmin(settings)
        rr.register_type(DataReady)
        rr.register_type(DataError)

    # -- Shared response validation ------------------------------------

    @staticmethod
    def _validate_response(resp: BaseModel, expected_type: DataRequestType) -> DataReady:
        """Return the DataReady reply; raise :class:`exceptions.DataError` for a DataError reply or a wrong type."""
        if isinstance(resp, DataError):
            raise exceptions.DataError(resp.error)
        if not isinstance(resp, DataReady) or resp.type != expected_type:
            raise exceptions.DataError(f"Expected {expected_type} DataReady, got {resp!r}")
        return resp

    # -- Historical (request → consume → return dict) ------------------

    async def request_historical[T](  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        symbols: list[str],
        asset: AssetType,
        data_type: MarketDataType,
        model_type: type[T],
        *,
        timeframe: Timeframe | None = None,
        days: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        timeout: float = 30.0,
    ) -> dict[str, list[T]]:
        """Send DataRequest for historical data, consume typed results.

        Returns ``{symbol: [T sorted by timestamp]}``. Raises :class:`exceptions.DataError` when
        announced records are missing and :class:`exceptions.TransportTimeoutError` when they
        cannot be read within ``timeout``.
        """
        start: datetime | None
        end: datetime | None
        if start_time is None and days is not None:
            end = end_time or datetime.now(UTC)
            start = end - timedelta(days=days)
        else:
            start = start_time
            end = end_time

        req = DataRequest(
            type=DataRequestType.HISTORIC,
            source_app=self._service_id,
            asset=asset,
            broker=self._broker,
            symbols=symbols,
            data_type=data_type,
            timeframe=timeframe or Timeframe.D1,
            start_time=start,
            end_time=end,
        )

        event_id = str(uuid.uuid4())  # ingestion stamps it on the reply and on every data record
        resp = self._validate_response(await self._rr.request(req, response_type=DataReady, event_id=event_id, timeout=timeout), DataRequestType.HISTORIC)
        logger.info("DataReady(historic): topic=%s record_count=%s", resp.data_topic, resp.record_count)

        expected = resp.record_count or 0
        if expected == 0:
            return {}

        await self._topic_admin.ensure(resp.data_topic)
        results: dict[str, list[T]] = {}
        received: set[int] = set()  # sequence numbers of this request's records

        consumer = TransportConsumer(resp.data_topic, self._settings, f"data-{uuid.uuid4().hex[:8]}", auto_offset_reset="earliest")
        try:
            async with asyncio.timeout(timeout):
                # Ingestion stores every record before it sends DataReady, so none is still on the way:
                # a record not found below these offsets was never written.
                watermarks = await consumer.watermarks()
                position = {partition: low for partition, (low, _) in watermarks.items()}
                while len(received) < expected and any(position[p] < high for p, (_, high) in watermarks.items()):
                    for msg in await consumer.poll():
                        position[msg.partition] = msg.offset + 1
                        if msg.headers.get(Header.EVENT_ID) != event_id:
                            continue
                        seq = int(msg.headers.get(Header.SEQUENCE, len(received)))  # unnumbered producers: count arrivals
                        if seq in received or not 0 <= seq < expected:
                            continue  # duplicate (e.g. ingestion re-ran the request) or not part of this DataReady
                        received.add(seq)
                        try:
                            item = model_type.model_validate_json(msg.payload)  # type: ignore[attr-defined]
                        except Exception:  # pylint: disable=broad-exception-caught
                            logger.debug("Skipping unparseable %s", data_type, exc_info=True)
                        else:
                            results.setdefault(item.symbol, []).append(item)  # type: ignore[union-attr]
        except TimeoutError as e:
            raise exceptions.TransportTimeoutError(f"Historical request {event_id}: {len(received)}/{expected} records after {timeout:.0f}s, {_missing(received, expected)}") from e
        finally:
            await consumer.close()

        if len(received) < expected:
            raise exceptions.DataError(f"Historical request {event_id}: {_missing(received, expected)} of {expected} records; {resp.data_topic} was read to its end without them")

        for symbol_items in results.values():
            symbol_items.sort(key=lambda b: b.timestamp)  # type: ignore[attr-defined]

        return results

    # -- Streaming (subscribe → yield indefinitely → unsubscribe) ------

    async def stream[T](  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        symbols: list[str],
        asset: AssetType,
        data_type: MarketDataType,
        model_type: type[T],
        *,
        timeframe: Timeframe | None = None,
        timeout: float = 30.0,
    ) -> StreamHandle[T]:
        """Send DataRequest for streaming, return a :class:`StreamHandle`.

        The returned handle supports both bare ``async for`` iteration
        and ``async with`` context-manager usage (recommended for
        guaranteed unsubscribe).
        """
        req = DataRequest(
            type=DataRequestType.STREAM,
            source_app=self._service_id,
            asset=asset,
            broker=self._broker,
            symbols=symbols,
            data_type=data_type,
            timeframe=timeframe or Timeframe.D1,
        )

        resp = self._validate_response(await self._rr.request(req, response_type=DataReady, timeout=timeout), DataRequestType.STREAM)

        await self._topic_admin.ensure(resp.data_topic)
        consumer = TransportConsumer(resp.data_topic, self._settings, f"stream-{uuid.uuid4().hex[:8]}")
        wanted = set(symbols)

        async def _consume() -> AsyncIterator[T]:
            try:
                async for msg in consumer:
                    if msg.key not in wanted:  # the stream topic carries every subscriber's symbols
                        continue
                    try:
                        parsed = model_type.model_validate_json(msg.payload)  # type: ignore[attr-defined]
                    except Exception:
                        continue
                    yield parsed
            finally:
                await consumer.close()

        unsubscribe = _Unsubscribe(
            faf=FireAndForget(TypedProducer(self._producer, self._topics.events.name), self._service_id),
            broker=self._broker,
            symbols=symbols,
            data_kind=data_type,
            asset=asset,
        )

        return StreamHandle(iterator=_consume(), unsubscribe=unsubscribe)


__all__ = ["_DataTransport"]
