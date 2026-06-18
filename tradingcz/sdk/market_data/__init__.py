"""Market data clients — historical and streaming stock/options data.

Public API:
  - ``StockDataClient`` — historical bars + streaming quotes/trades
  - ``OptionsDataClient`` — option snapshots
  - ``CorporateActionsClient`` — dividends, splits, capital events
  - ``TimeKeeper`` — market clock with pre-close warning events
  - ``MarketClockProvider`` — protocol for market clock implementations
"""

from tradingcz.sdk.market_data.stock import StockDataClient
from tradingcz.sdk.market_data.options import OptionsDataClient
from tradingcz.sdk.market_data.corporate import CorporateActionsClient
from tradingcz.sdk.market_data.clock import TimeKeeper, MarketClockProvider

__all__ = [
    "StockDataClient",
    "OptionsDataClient",
    "CorporateActionsClient",
    "TimeKeeper",
    "MarketClockProvider",
]
