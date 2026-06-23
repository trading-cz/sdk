"""StockStreamClient — streaming stock market data."""

# pylint: disable=protected-access

from __future__ import annotations

import logging

from tradingcz.sdk.market_data._internal._stream_handle import StreamHandle
from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, Broker, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.market import Bar, Quote, Trade
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer

logger = logging.getLogger(__name__)


class StockStreamClient:
    """Stream live stock market data via RequestReply."""

    def __init__(
        self,
        *,
        rr: RequestReply | None = None,
        producer: TransportProducer | None = None,
        settings: KafkaSettings | None = None,
        topics: KafkaTopicRegistry | None = None,
        service_id: str = "",
        broker: Broker = Broker.ALPACA,
        _transport: _DataTransport | None = None,
    ) -> None:
        if _transport is not None:
            self._transport = _transport
        elif rr is not None and producer is not None and settings is not None and topics is not None:
            self._transport = _DataTransport(
                rr=rr, producer=producer, settings=settings, topics=topics,
                service_id=service_id, broker=broker,
            )
        else:
            raise ValueError("Provide _transport or (rr, producer, settings, topics, service_id)")

    async def stream_quotes(
        self, symbols: list[str], *, timeout: float = 30.0
    ) -> StreamHandle[Quote]:
        """Stream live bid/ask quotes."""
        return await self._transport.stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.QUOTES,
            model_type=Quote,
            timeout=timeout,
        )

    async def stream_bars(
        self,
        symbols: list[str],
        *,
        timeframe: Timeframe = Timeframe.H4,
        timeout: float = 30.0,
    ) -> StreamHandle[Bar]:
        """Stream live bar closes (OHLCV aggregates)."""
        logger.info(
            "StockStreamClient: stream_bars symbols=%d timeframe=%s",
            len(symbols), timeframe,
        )
        return await self._transport.stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.BARS,
            model_type=Bar,
            timeframe=timeframe,
            timeout=timeout,
        )

    async def stream_trades(
        self, symbols: list[str], *, timeout: float = 30.0
    ) -> StreamHandle[Trade]:
        """Stream live trade ticks."""
        return await self._transport.stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.TRADES,
            model_type=Trade,
            timeout=timeout,
        )


__all__ = ["StockStreamClient"]
