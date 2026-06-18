"""StockDataClient — historical bars + latest quotes + streaming.

One-time (returns ``dict``):
  - ``bars()``          — OHLCV aggregates for a time range
  - ``latest_quotes()`` — most recent bid/ask per symbol (poll-friendly)

Streaming (returns :class:`StreamHandle`):
  - ``stream_quotes()`` — live bid/ask quotes, yields indefinitely
  - ``stream_trades()`` — live trade ticks, yields indefinitely
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging

from tradingcz.sdk.models.enums.event import AssetType, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.models.market import Bar, Quote, StreamQuote, Trade

from tradingcz.sdk.market_data._base import BaseDataClient, StreamHandle

logger = logging.getLogger(__name__)


class StockDataClient:
    """Request and consume stock market data.

    All methods are async and return typed domain objects.
    No Kafka knowledge required.

    **One-time data** (returns a plain ``dict``)::

        bars = await app.stock.bars(["AAPL", "MSFT"], days=30)
        for symbol, daily_bars in bars.items():
            print(f"{symbol}: {len(daily_bars)} bars")

    **Streaming data** (returns a :class:`StreamHandle`)::

        # Bare iteration — cleanup on loop exit
        async for quote in app.stock.stream_quotes(["AAPL"]):
            print(quote.quote.bid_price)
            if done:
                break

        # Context manager — guaranteed unsubscribe
        async with app.stock.stream_quotes(["AAPL"]) as stream:
            async for quote in stream:
                ...
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    # -- One-time ------------------------------------------------------

    async def bars(self, symbols: list[str], *, days: int, timeframe: str, timeout: float = 30.0) -> dict[str, list[Bar]]:
        """Request historical OHLCV bars.

        Returns ``{symbol: [Bar sorted by timestamp]}``.
        """
        logger.info("StockDataClient: bars symbols=%d days=%d timeframe=%s", len(symbols), days, timeframe)
        return await self._base._request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.BARS,
            model_type=Bar,
            timeframe=timeframe,
            days=days,
            timeout=timeout,
        )

    # -- Latest (poll-friendly, no streaming) ---------------------------

    async def latest_quotes(self, symbols: list[str], *, timeout: float = 5.0) -> dict[str, Quote]:
        """Request the most recent quote for each symbol.

        Returns ``{symbol: Quote}`` — exactly one quote per symbol
        (the latest available).  Use for polling-based price checks
        where streaming every tick is unnecessary overhead.

        Uses ``MarketDataType.LATEST_QUOTES`` — ingestion returns the
        most recent bid/ask without opening a persistent stream.
        """
        logger.info("StockDataClient: latest_quotes symbols=%d", len(symbols))
        result = await self._base._request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.LATEST_QUOTES,
            model_type=Quote,
            timeout=timeout,
        )
        # _request_historical returns dict[symbol, list[T]] — flatten to one per symbol
        return {sym: quotes[-1] for sym, quotes in result.items() if quotes}

    # -- Streaming -----------------------------------------------------

    async def stream_quotes(self, symbols: list[str], *, timeout: float = 30.0) -> StreamHandle[StreamQuote]:
        """Stream live bid/ask quotes.

        Returns a :class:`StreamHandle` that yields :class:`StreamQuote`
        objects indefinitely.  Use ``async for`` to iterate, or wrap
        in ``async with`` for guaranteed unsubscribe on exit.
        logger.info("StockDataClient: stream_quotes symbols=%d", len(symbols))
        """
        return await self._base._stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.QUOTES,
            model_type=StreamQuote,
            timeout=timeout,
        )

    async def stream_bars(self, symbols: list[str], *, timeframe: Timeframe = Timeframe.H4, timeout: float = 30.0) -> StreamHandle[Bar]:
        """Stream live bar closes (OHLCV aggregates).

        Returns a :class:`StreamHandle` that yields :class:`Bar`
        objects indefinitely.  Use ``async for`` to iterate, or wrap
        in ``async with`` for guaranteed unsubscribe on exit.

        Args:
            symbols: List of ticker symbols to stream.
            timeframe: Candle timeframe from :class:`Timeframe` enum.  Default ``H4`` (4-hour).
            timeout: Seconds to wait for the DataReady response.
        """
        logger.info("StockDataClient: stream_bars symbols=%d timeframe=%s", len(symbols), timeframe)
        return await self._base._stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.BARS,
            model_type=Bar,
            timeframe=timeframe,
            timeout=timeout,
        )

    async def stream_trades(self, symbols: list[str], *, timeout: float = 30.0) -> StreamHandle[Trade]:
        """Stream live trade ticks.

        Returns a :class:`StreamHandle` that yields :class:`Trade`
        objects indefinitely.  Use ``async for`` to iterate, or wrap
        in ``async with`` for guaranteed unsubscribe on exit.
        logger.info("StockDataClient: stream_trades symbols=%d", len(symbols))
        """
        return await self._base._stream(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.TRADES,
            model_type=Trade,
            timeout=timeout,
        )


__all__ = ["StockDataClient"]
