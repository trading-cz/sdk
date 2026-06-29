"""StockDataProvider — abstract contract for stock market data fetching.

This is the SINGLE contract that both sides of the data pipeline implement:

* **Consumer side** — :class:`StockDataClient` sends DataRequests to Kafka
* **Provider side** — ingestion adapters fetch from external brokers (Alpaca, etc.)

Both inherit from this ABC.  Adding a method here forces BOTH sides to
implement it — the contract stays in sync by construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from tradingcz.sdk.models.market import Bar, Quote, Snapshot, Trade


class StockDataProvider(ABC):
    """Abstract contract for fetching stock market data.

    Every method returns a ``dict[symbol, items]`` keyed by symbol.

    **Two implementations exist — one ABC, one contract:**

    * :class:`StockDataClient` — Kafka proxy (consumer side)
    * Ingestion adapters — direct broker API calls (provider side)

    Both are forced to stay in sync because they inherit from this class.
    """

    # -- Historical (time-range) ---------------------------------------

    @abstractmethod
    async def get_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> dict[str, list[Bar]]:
        """Fetch historical OHLCV bars for *symbols* in [*start*, *end*]."""

    @abstractmethod
    async def get_trades(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Trade]]:
        """Fetch individual trades for *symbols* in [*start*, *end*]."""

    @abstractmethod
    async def get_quotes(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Quote]]:
        """Fetch bid/ask quotes for *symbols* in [*start*, *end*]."""

    @abstractmethod
    async def get_snapshots(
        self,
        symbols: list[str],
    ) -> dict[str, Snapshot]:
        """Fetch multi-part snapshots (latest trade/quote/bars) for *symbols*."""

    # -- Latest (single item per symbol, no time range) ----------------

    @abstractmethod
    async def get_latest_bars(
        self,
        symbols: list[str],
    ) -> dict[str, Bar]:
        """Fetch the most recent minute bar for each symbol."""

    @abstractmethod
    async def get_latest_trades(
        self,
        symbols: list[str],
    ) -> dict[str, Trade]:
        """Fetch the most recent trade for each symbol."""

    @abstractmethod
    async def get_latest_quotes(
        self,
        symbols: list[str],
    ) -> dict[str, Quote]:
        """Fetch the most recent quote for each symbol."""


__all__ = ["StockDataProvider"]
