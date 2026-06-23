"""Internal transport layer — request/reply + typed consumption.

Application code never references this module directly.
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from tradingcz.sdk.market_data._internal._stream_handle import StreamHandle, _Unsubscribe
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import (
    AssetType,
    Broker,
    DataRequestType,
    EventType,
    MarketDataType,
)
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.events import DataError, DataReady, DataRequest
from tradingcz.sdk.transport.dedup import DedupFilter
from tradingcz.sdk.transport.kafka_header import Header
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.typed.single_type_consumer import SingleTypeConsumer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


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
        *,
        dedup_max_size: int = 100_000,
    ) -> None:
        self._rr = rr
        self._producer = producer
        self._settings = settings
        self._topics = topics
        self._service_id = service_id
        self._broker = broker
        self._dedup = DedupFilter(max_size=dedup_max_size)
        self._topic_admin = KafkaTopicAdmin(settings)
        rr.register_type(EventType.DATA_READY, DataReady)
        rr.register_type(EventType.DATA_ERROR, DataError)

    # -- Shared response validation ------------------------------------

    @staticmethod
    def _validate_response(resp: DataReady, expected_type: DataRequestType) -> None:
        """Validate DataReady response — raise on wrong type."""
        if resp.type != expected_type:
            raise RuntimeError(f"Expected {expected_type} DataReady, got type={resp.type}")

    # -- Shared data-topic consumer -----------------------------------

    async def _consume_typed[T](
        self, topic: str, model_type: type[T], group: str, *, event_id: str = "",
    ) -> AsyncIterator[T]:
        """Iterate typed, deduped messages from a single-type data topic.

        Uses :class:`SingleTypeConsumer` for JSON parsing and event_id
        filtering.  Dedup is applied in the caller loop via raw headers.
        """
        consumer = SingleTypeConsumer(
            topic=topic,
            settings=self._settings,
            model_type=model_type,
            group_suffix=group,
            auto_commit=False,
            header_filter=lambda h: h.get(Header.EVENT_ID) == event_id
            if event_id
            else True,
        )
        async for _event_type, model, raw in consumer:
            # ── Dedup (transport-layer concern) ──
            seq = raw.headers.get(Header.SEQUENCE, "")
            if seq and self._dedup.is_duplicate(
                raw.headers.get(
                    Header.SOURCE,
                    raw.headers.get(Header.SOURCE_APP, ""),
                ),
                seq,
            ):
                continue
            yield model

    # -- Historical (request → consume → return dict) ------------------

    async def request_historical[T](  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        symbols: list[str],
        asset: AssetType,
        data_type: MarketDataType,
        model_type: type[T],
        timeframe: Timeframe,
        *,
        days: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        timeout: float = 30.0,
    ) -> dict[str, list[T]]:
        """Send DataRequest for historical data, consume typed results.

        Returns ``{symbol: [T sorted by timestamp]}``.
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
            timeframe=timeframe,
            start_time=start,
            end_time=end,
        )

        resp = await self._rr.request(req, response_type=DataReady, request_type=EventType.DATA_REQUEST, timeout=timeout)

        self._validate_response(resp, DataRequestType.HISTORIC)
        logger.info("DataReady(historic): topic=%s record_count=%s", resp.data_topic, resp.record_count)

        await self._topic_admin.ensure(resp.data_topic)
        results: dict[str, list[T]] = {}
        count = 0
        expected = resp.record_count or 0

        async for item in self._consume_typed(
            resp.data_topic, model_type, "data", event_id=str(req.event_id),
        ):
            results.setdefault(item.symbol, []).append(item)  # type: ignore[union-attr]
            count += 1
            if expected and count >= expected:
                break

        for symbol_items in results.values():
            symbol_items.sort(key=lambda b: b.timestamp)  # type: ignore[attr-defined]

        return results

    # -- Streaming (subscribe → yield indefinitely → unsubscribe) ------

    async def stream[
        T
    ](  # pylint: disable=too-many-arguments,too-many-positional-arguments
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

        resp = await self._rr.request(
            req,
            response_type=DataReady,
            request_type=EventType.DATA_REQUEST,
            timeout=timeout,
        )

        self._validate_response(resp, DataRequestType.STREAM)

        await self._topic_admin.ensure(resp.data_topic)

        async def _consume() -> AsyncIterator[T]:
            async for item in self._consume_typed(resp.data_topic, model_type, "stream"):
                yield item

        unsubscribe = _Unsubscribe(
            producer=TypedProducer(self._producer, self._topics.events.name),
            service_id=self._service_id,
            broker=self._broker,
            symbols=symbols,
            data_kind=data_type,
            asset=asset,
        )

        return StreamHandle(iterator=_consume(), unsubscribe=unsubscribe)


__all__ = ["_DataTransport"]
