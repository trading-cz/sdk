"""StockDataClient — historical bars + streaming quotes/trades.

One-time (returns ``dict``):
  - ``bars()``     — OHLCV aggregates for a time range

Streaming (returns :class:`StreamHandle`):
  - ``stream_quotes()``   — live bid/ask quotes, yields indefinitely
  - ``stream_trades()``   — live trade ticks, yields indefinitely
"""

# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING

from tradingcz.sdk.models.enums.event import MarketDataType
from tradingcz.sdk.models.market import Bar, StreamQuote, Trade

if TYPE_CHECKING:
    from tradingcz.sdk.market_data._base import BaseDataClient, StreamHandle


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

    async def bars(
        self,
        symbols: list[str],
        *,
        days: int = 14,
        timeframe: str = "1d",
        timeout: float = 30.0,
    ) -> dict[str, list[Bar]]:
        """Request historical OHLCV bars.

        Returns ``{symbol: [Bar sorted by timestamp]}``.
        """
        return await self._base._request_historical(
            symbols=symbols,
            asset="stock",
            data_kind=MarketDataType.BARS,
            model_type=Bar,
            timeframe=timeframe,
            days=days,
            timeout=timeout,
        )

    # -- Streaming -----------------------------------------------------

    async def stream_quotes(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> StreamHandle[StreamQuote]:
        """Stream live bid/ask quotes.

        Returns a :class:`StreamHandle` that yields :class:`StreamQuote`
        objects indefinitely.  Use ``async for`` to iterate, or wrap
        in ``async with`` for guaranteed unsubscribe on exit.
        """
        return await self._base._stream(
            symbols=symbols,
            asset="stock",
            data_kind=MarketDataType.QUOTES,
            model_type=StreamQuote,
            timeout=timeout,
        )

    async def stream_trades(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> StreamHandle[Trade]:
        """Stream live trade ticks.

        Returns a :class:`StreamHandle` that yields :class:`Trade`
        objects indefinitely.  Use ``async for`` to iterate, or wrap
        in ``async with`` for guaranteed unsubscribe on exit.
        """
        return await self._base._stream(
            symbols=symbols,
            asset="stock",
            data_kind=MarketDataType.TRADES,
            model_type=Trade,
            timeout=timeout,
        )


__all__ = ["StockDataClient"]
