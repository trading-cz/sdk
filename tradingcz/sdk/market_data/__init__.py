"""Market data clients — historical and streaming stock/options data.

Public API:
  - ``StockDataClient`` — historical bars + latest quotes/trades/bars
  - ``StockStreamClient`` — streaming quotes/bars/trades
  - ``OptionsHistoricDataClient`` — option snapshots
  - ``CorporateActionsClient`` — dividends, splits, capital events
  - ``TimeKeeper`` — market clock with pre-close warning events
  - ``MarketClockProvider`` — protocol for market clock implementations

Provider contracts (for implementors like ingestion adapters):
  - ``StockDataProvider`` — ABC for stock data fetching
  - ``OptionDataProvider`` — ABC for option data fetching
"""

from tradingcz.sdk.market_data._internal.option_data_provider import OptionDataProvider
from tradingcz.sdk.market_data._internal.stock_data_provider import StockDataProvider
from tradingcz.sdk.market_data.clock import MarketClockProvider, TimeKeeper
from tradingcz.sdk.market_data.corporate import CorporateActionsClient
from tradingcz.sdk.market_data.option_historic import OptionsHistoricDataClient
from tradingcz.sdk.market_data.stock_historic import StockDataClient
from tradingcz.sdk.market_data.stock_stream import StockStreamClient

__all__ = [
    "StockDataClient",
    "StockStreamClient",
    "OptionsHistoricDataClient",
    "CorporateActionsClient",
    "TimeKeeper",
    "MarketClockProvider",
    "StockDataProvider",
    "OptionDataProvider",
]
