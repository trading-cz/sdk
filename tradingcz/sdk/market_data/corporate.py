"""CorporateActionsClient — dividends, splits, and capital events.

One-time (returns ``dict``):
  - ``dividends()`` — dividend history for symbols
  - ``splits()``    — stock split history for symbols
"""

from __future__ import annotations

from tradingcz.sdk.market_data._base import BaseDataClient
from tradingcz.sdk.models.enums.event import MarketDataType
from tradingcz.sdk.models.market.corporate import Dividend, StockSplit


class CorporateActionsClient:
    """Request corporate actions (dividends, splits, etc.).

    Usage::

        async with TradingApp(service_id="risk-checker") as app:
            divs = await app.corporate_actions.dividends(["AAPL"], days=365)
            splits = await app.corporate_actions.splits(["AAPL"], days=365)
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    async def dividends(
        self, symbols: list[str], *, days: int = 365, timeout: float = 30.0,
    ) -> dict[str, list[Dividend]]:
        """Request dividend history for symbols.

        Returns ``{symbol: [Dividend sorted by ex_date]}``.
        """
        # pylint: disable=protected-access
        return await self._base._request_historical(
            symbols=symbols,
            asset="stock",
            data_type=MarketDataType.DIVIDENDS,
            model_type=Dividend,
            days=days,
            timeout=timeout,
        )

    async def splits(
        self, symbols: list[str], *, days: int = 365, timeout: float = 30.0,
    ) -> dict[str, list[StockSplit]]:
        """Request stock split history for symbols.

        Returns ``{symbol: [StockSplit sorted by ex_date]}``.
        """
        # pylint: disable=protected-access
        return await self._base._request_historical(
            symbols=symbols,
            asset="stock",
            data_type=MarketDataType.SPLITS,
            model_type=StockSplit,
            days=days,
            timeout=timeout,
        )


__all__ = ["CorporateActionsClient"]
