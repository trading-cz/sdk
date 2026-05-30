"""CorporateActionsClient — dividends, splits, and capital events.

One-time (returns ``dict``):
  - ``dividends()`` — dividend history for symbols
  - ``splits()``    — stock split history for symbols

Note: models for corporate actions data are not yet finalized.
This module is a placeholder demonstrating the pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingcz.sdk.data._base import _BaseDataClient


class CorporateActionsClient:
    """Request corporate actions (dividends, splits, etc.).

    Usage::

        async with TradingApp(service_id="risk-checker") as app:
            divs = await app.corporate_actions.dividends(["AAPL"])
    """

    def __init__(self, base: _BaseDataClient) -> None:
        self._base = base

    async def dividends(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> dict[str, list]:
        """Request dividend history for symbols.

        Returns ``{symbol: [dividend events]}``.
        """
        raise NotImplementedError(
            "Corporate actions data models are not yet defined. "
            "See tradingcz.model.corporate (planned)."
        )

    async def splits(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> dict[str, list]:
        """Request stock split history for symbols.

        Returns ``{symbol: [split events]}``.
        """
        raise NotImplementedError(
            "Corporate actions data models are not yet defined. "
            "See tradingcz.model.corporate (planned)."
        )
