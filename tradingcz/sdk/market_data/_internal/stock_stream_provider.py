"""StockStreamProvider — abstract contract for live stock data streaming.

Concrete implementations must implement subscribe, unsubscribe, stream, and close.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from tradingcz.sdk.models.market import Bar, Quote, Trade


class StockStreamProvider(ABC):
    """Abstract contract for streaming live stock market data.

    Ingestion adapters implement this to connect to broker WebSockets.
    The stream handler depends on this ABC — no METHOD_MAP, no hasattr.
    """

    @abstractmethod
    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to live data for *symbols*."""

    @abstractmethod
    async def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from live data for *symbols*."""

    @abstractmethod
    async def stream(self) -> AsyncIterator[Bar | Trade | Quote]:
        """Yield live market data items continuously until ``close()``."""
        # async generator stub — subclasses must yield
        return
        yield  # pragma: no cover  # noqa: B909

    @abstractmethod
    async def close(self) -> None:
        """Release all resources (WebSocket, tasks, etc.)."""


__all__ = ["StockStreamProvider"]
