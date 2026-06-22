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

from tradingcz.sdk.market_data._base import BaseDataClient
from tradingcz.sdk.models.enums.event import AssetType, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.market import Bar, Quote, Trade

logger = logging.getLogger(__name__)


class StockDataClient:
    """Request historical and latest stock market data.

    All methods are async and return typed domain objects.
    No Kafka knowledge required.
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    # -- Historical ----------------------------------------------------

    async def bars(
        self, symbols: list[str], *, days: int, timeframe: str, timeout: float = 30.0
    ) -> dict[str, list[Bar]]:
        """Request historical OHLCV bars."""
        logger.info(
            "StockDataClient: bars symbols=%d days=%d timeframe=%s",
            len(symbols), days, timeframe,
        )
        return await self._base._request_historical(
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
        result = await self._base._request_historical(
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
        result = await self._base._request_historical(
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
        result = await self._base._request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.LATEST_BARS,
            model_type=Bar,
            timeout=timeout,
        )
        return {sym: bars[-1] for sym, bars in result.items() if bars}


__all__ = ["StockDataClient"]
