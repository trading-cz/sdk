"""StockDataClient — Kafka-backed implementation of :class:`StockDataProvider`.

Implements the ABC by sending DataRequests to Kafka and consuming typed
results from the ingestion service.
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging
from datetime import datetime

from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.market_data._internal.stock_data_provider import StockDataProvider
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, Broker, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.market import Bar, Quote, Snapshot, Trade
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer

logger = logging.getLogger(__name__)


class StockDataClient(StockDataProvider):
    """Request historical and latest stock market data via Kafka."""

    def __init__(
        self,
        *,
        rr: RequestReply,
        producer: TransportProducer,
        settings: KafkaSettings,
        topics: KafkaTopicRegistry,
        service_id: str,
        broker: Broker = Broker.ALPACA,
        default_timeout: float = 30.0,
        _transport: _DataTransport | None = None,
    ) -> None:
        self._default_timeout = default_timeout
        if _transport is not None:
            self._transport = _transport
        else:
            self._transport = _DataTransport(
                rr=rr, producer=producer, settings=settings, topics=topics,
                service_id=service_id, broker=broker,
            )

    # -- ABC implementation --------------------------------------------

    async def get_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> dict[str, list[Bar]]:
        logger.info("StockDataClient: get_bars symbols=%d timeframe=%s", len(symbols), timeframe)
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.BARS,
            model_type=Bar,
            start_time=start,
            end_time=end,
            timeout=self._default_timeout,
            timeframe=Timeframe(timeframe),
        )

    async def get_trades(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Trade]]:
        logger.info("StockDataClient: get_trades symbols=%d", len(symbols))
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.TRADES,
            model_type=Trade,
            start_time=start,
            end_time=end,
            timeout=self._default_timeout,
        )

    async def get_quotes(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Quote]]:
        logger.info("StockDataClient: get_quotes symbols=%d", len(symbols))
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.QUOTES,
            model_type=Quote,
            start_time=start,
            end_time=end,
            timeout=self._default_timeout,
        )

    async def get_snapshots(
        self,
        symbols: list[str],
    ) -> dict[str, Snapshot]:
        logger.info("StockDataClient: get_snapshots symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.SNAPSHOTS,
            model_type=Snapshot,
            timeout=self._default_timeout,
        )
        return {sym: items[-1] for sym, items in result.items() if items}

    async def get_latest_bars(
        self,
        symbols: list[str],
    ) -> dict[str, Bar]:
        logger.info("StockDataClient: get_latest_bars symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.BARS,
            model_type=Bar,
            latest_only=True,
            timeout=self._default_timeout,
        )
        return {sym: bars[-1] for sym, bars in result.items() if bars}

    async def get_latest_trades(
        self,
        symbols: list[str],
    ) -> dict[str, Trade]:
        logger.info("StockDataClient: get_latest_trades symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.TRADES,
            model_type=Trade,
            latest_only=True,
            timeout=self._default_timeout,
        )
        return {sym: trades[-1] for sym, trades in result.items() if trades}

    async def get_latest_quotes(
        self,
        symbols: list[str],
    ) -> dict[str, Quote]:
        logger.info("StockDataClient: get_latest_quotes symbols=%d", len(symbols))
        result = await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.QUOTES,
            model_type=Quote,
            latest_only=True,
            timeout=self._default_timeout,
        )
        return {sym: quotes[-1] for sym, quotes in result.items() if quotes}


__all__ = ["StockDataClient"]
