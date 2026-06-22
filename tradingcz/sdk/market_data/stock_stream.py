"""StockStreamClient — streaming stock market data.

Streaming (returns ``StreamHandle[T]``):
  - ``stream_quotes()`` — live bid/ask quotes
  - ``stream_bars()`` — live bar closes (OHLCV aggregates)
  - ``stream_trades()`` — live trade ticks
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging

from tradingcz.sdk.market_data._base import BaseDataClient, StreamHandle
from tradingcz.sdk.models.enums.event import AssetType, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.market import Bar, Quote, Trade

logger = logging.getLogger(__name__)


class StockStreamClient:
    """Stream live stock market data.

    All methods return a :class:`StreamHandle` that supports both
    bare ``async for`` iteration and context-manager usage (guaranteed
    unsubscribe on exit).

    **Streaming** (returns :class:`StreamHandle[T]`)::

        async with app.stock_stream.stream_quotes(["AAPL"]) as stream:
            async for quote in stream:
                if quote.bid_price > threshold:
                    break
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    async def stream_quotes(
        self, symbols: list[str], *, timeout: float = 30.0
    ) -> StreamHandle[Quote]:
        """Stream live bid/ask quotes."""
        return await self._base._stream(
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
        return await self._base._stream(
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
        return await self._base._stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.TRADES,
            model_type=Trade,
            timeout=timeout,
        )


__all__ = ["StockStreamClient"]
