"""StockDataClient — historical bars + latest quotes (one-time requests).

One-time (returns ``dict``):
  - ``bars()`` — historical OHLCV bars
  - ``latest_quotes()`` — most recent quote per symbol
  - ``latest_trades()`` — most recent trade per symbol
  - ``latest_bars()`` — most recent minute bar per symbol
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging

from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, Broker, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.market import Bar, Quote, Trade
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer

logger = logging.getLogger(__name__)


class StockDataClient:
    """Request historical and latest stock market data.

    Constructor args::

        StockDataClient(
            rr=request_reply,           # RequestReply instance (started)
            producer=transport_producer, # TransportProducer for fire-and-forget
            settings=kafka_settings,    # KafkaSettings
            topics=topic_registry,      # KafkaTopicRegistry
            service_id="my-service",    # unique service identifier
            broker=Broker.ALPACA,       # optional, default: ALPACA
        )

    All methods are async and return typed domain objects.
    No Kafka knowledge required beyond the constructor.
    """

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

    # -- Historical ----------------------------------------------------

    async def bars(
        self, symbols: list[str], *, days: int, timeframe: str, timeout: float = 30.0
    ) -> dict[str, list[Bar]]:
        """Request historical OHLCV bars."""
        logger.info(
            "StockDataClient: bars symbols=%d days=%d timeframe=%s",
            len(symbols), days, timeframe,
        )
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.BARS,
            model_type=Bar,
            timeframe=Timeframe(timeframe),
            days=days,
            timeout=timeout,
        )

    # -- Latest (poll-friendly, no streaming) ---------------------------

    async def latest_quotes(self, symbols: list[str], *, timeout: float = 5.0) -> dict[str, Quote]:
        """Request the most recent quote for each symbol."""
        logger.info("StockDataClient: latest_quotes symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.LATEST_QUOTES,
            model_type=Quote,
            timeout=timeout,
        )
        return {sym: quotes[-1] for sym, quotes in result.items() if quotes}

    async def latest_trades(self, symbols: list[str], *, timeout: float = 5.0) -> dict[str, Trade]:
        """Request the most recent trade for each symbol."""
        logger.info("StockDataClient: latest_trades symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.LATEST_TRADES,
            model_type=Trade,
            timeout=timeout,
        )
        return {sym: trades[-1] for sym, trades in result.items() if trades}

    async def latest_bars(self, symbols: list[str], *, timeout: float = 5.0) -> dict[str, Bar]:
        """Request the most recent minute bar for each symbol."""
        logger.info("StockDataClient: latest_bars symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.LATEST_BARS,
            model_type=Bar,
            timeout=timeout,
        )
        return {sym: bars[-1] for sym, bars in result.items() if bars}


__all__ = ["StockDataClient"]
