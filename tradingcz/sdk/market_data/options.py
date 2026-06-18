"""OptionsDataClient — option snapshots and bars.

One-time (returns ``dict``):
  - ``snapshots()`` — latest trade, quote, greeks, IV for given symbols
"""

# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING

from tradingcz.sdk.models.enums.event import AssetType, MarketDataType
from tradingcz.sdk.models.market import OptionSnapshot

if TYPE_CHECKING:
    from tradingcz.sdk.market_data._base import BaseDataClient


class OptionsDataClient:
    """Request and consume options market data.

    All methods are async and return typed domain objects.
    No Kafka knowledge required.

    **One-time data** (returns a plain ``dict``)::

        # Single snapshot
        snaps = await app.options.snapshots(["AAPL250620C00150000"])
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    async def snapshots(self, symbols: list[str], *, timeout: float = 30.0) -> dict[str, list[OptionSnapshot]]:
        """Request option snapshots (trade, quote, greeks, IV).

        Returns ``{symbol: [OptionSnapshot]}``.
        """
        return await self._base._request_historical(
            symbols=symbols,
            asset=AssetType.OPTION,
            data_kind=MarketDataType.SNAPSHOTS,
            model_type=OptionSnapshot,
            timeout=timeout,
        )


__all__ = ["OptionsDataClient"]
