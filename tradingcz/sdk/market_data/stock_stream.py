"""StockStreamClient — streaming stock market data.

Streaming (returns ``StreamHandle[T]``):
  - ``stream_quotes()`` — live bid/ask quotes
  - ``stream_bars()`` — live bar closes (OHLCV aggregates)
  - ``stream_trades()`` — live trade ticks
"""

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
    """Stream live stock market data."""

    def __init__(
        self,
        *,
        rr: RequestReply,
        producer: TransportProducer,
        settings: KafkaSettings,
        topics: KafkaTopicRegistry,
        service_id: str,
        broker: Broker = Broker.ALPACA,
        _transport: _DataTransport | None = None,
    ) -> None:
        if _transport is not None:
            self._transport = _transport
        else:
            self._transport = _DataTransport(
                rr=rr, producer=producer, settings=settings, topics=topics,
                service_id=service_id, broker=broker,
            )

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
