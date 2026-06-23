"""OptionDataProvider — abstract contract for option market data fetching.

Concrete implementations must implement every method defined here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from tradingcz.sdk.models.market import Bar, OptionSnapshot, Trade


class OptionDataProvider(ABC):
    """Abstract contract for fetching option market data."""

    @abstractmethod
    async def get_snapshots(
        self,
        symbols: list[str],
    ) -> dict[str, list[OptionSnapshot]]:
        """Fetch option snapshots (Greeks, latest trade/quote) for *symbols*."""

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


__all__ = ["OptionDataProvider"]
