"""OptionDataProvider — abstract contract for option market data fetching.

Concrete implementations must implement every method defined here.

Only methods that Alpaca actually provides are included — no speculative
"maybe someday" methods.  Future brokers (Polygon, IBKR) implement what
they can; unsupported methods raise ``NotImplementedError``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from tradingcz.sdk.models.market import Bar, OptionSnapshot, Quote, Trade


class OptionDataProvider(ABC):
    """Abstract contract for fetching option market data.

    Every method maps to a real Alpaca endpoint.  Other brokers implement
    the subset they support — handlers catch ``NotImplementedError`` for
    unsupported data types.
    """

    # -- Snapshots (greeks + latest trade/quote) -----------------------

    @abstractmethod
    async def get_snapshots(
        self,
        symbols: list[str],
    ) -> dict[str, list[OptionSnapshot]]:
        """Fetch option snapshots (Greeks, latest trade/quote) for *symbols*."""

    # -- Historical (time-range) ---------------------------------------

    @abstractmethod
    async def get_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> dict[str, list[Bar]]:
        """Fetch historical OHLCV bars for option *symbols* in [*start*, *end*]."""

    @abstractmethod
    async def get_trades(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Trade]]:
        """Fetch individual trades for option *symbols* in [*start*, *end*]."""

    # -- Latest (single item per symbol, no time range) ----------------

    @abstractmethod
    async def get_latest_quotes(
        self,
        symbols: list[str],
    ) -> dict[str, Quote]:
        """Fetch the most recent quote for each option symbol."""

    @abstractmethod
    async def get_latest_trades(
        self,
        symbols: list[str],
    ) -> dict[str, Trade]:
        """Fetch the most recent trade for each option symbol."""


__all__ = ["OptionDataProvider"]
