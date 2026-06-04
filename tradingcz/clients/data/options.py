"""OptionsDataClient — option snapshots, chain, and bars.

One-time (returns ``dict``):
  - ``snapshots()`` — latest trade, quote, greeks, IV for given symbols
  - ``chain()``     — all contracts for an underlying
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tradingcz.models.market import OptionSnapshot

if TYPE_CHECKING:
    from tradingcz.clients.base import BaseDataClient


class OptionsDataClient:
    """Request and consume options market data.

    All methods are async and return typed domain objects.
    No Kafka knowledge required.

    **One-time data** (returns a plain ``dict``)::

        # Single snapshot
        snaps = await app.options.snapshots(["AAPL250620C00150000"])

        # Full chain
        chain = await app.options.chain("AAPL")
        for symbol, snap in chain.items():
            if snap.implied_volatility and snap.implied_volatility > 0.3:
                print(f"High IV: {symbol} IV={snap.implied_volatility:.2%}")
    """

    def __init__(self, base: BaseDataClient) -> None:
        self._base = base

    async def snapshots(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> dict[str, OptionSnapshot]:
        """Request option snapshots (trade, quote, greeks, IV).

        Returns ``{symbol: OptionSnapshot}``.
        """
        return await self._base._request_historical(
            symbols=symbols,
            asset="option",
            data_type="snapshots",
            model_type=OptionSnapshot,
            timeout=timeout,
        )

    async def chain(
        self,
        underlying: str,
        *,
        timeout: float = 30.0,
    ) -> dict[str, OptionSnapshot]:
        """Request all option contracts for an underlying.

        Returns ``{contract_symbol: OptionSnapshot}`` for all active
        contracts.
        """
        return await self._base._request_historical(
            symbols=[underlying],
            asset="option",
            data_type="chain",
            model_type=OptionSnapshot,
            timeout=timeout,
        )
