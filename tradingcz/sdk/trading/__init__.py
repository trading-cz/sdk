"""tradingcz.sdk.trading — re-exports for backward compatibility.

Prefer importing from the canonical new locations:
  - ``TradingApp`` → ``tradingcz.sdk`` (root)
  - ``ServiceApp`` → ``tradingcz.sdk`` (root)
  - Data clients → ``tradingcz.sdk.market_data``
  - Account clients → ``tradingcz.sdk.account``
"""

from tradingcz.sdk.service_app import ServiceApp
from tradingcz.sdk.trading_app import TradingApp
from tradingcz.sdk.account.balance import BalanceClient
from tradingcz.sdk.account.orders import OrderClient
from tradingcz.sdk.account.positions import PositionClient
from tradingcz.sdk.market_data.corporate import CorporateActionsClient
from tradingcz.sdk.market_data.options import OptionsDataClient
from tradingcz.sdk.account.signals import SignalPublisher
from tradingcz.sdk.market_data.stock import StockDataClient
from tradingcz.sdk.market_data.clock import MarketClockProvider, TimeKeeper

__all__ = [
    "TradingApp",
    "ServiceApp",
    # market data
    "StockDataClient",
    "OptionsDataClient",
    "CorporateActionsClient",
    # account state
    "BalanceClient",
    "OrderClient",
    "PositionClient",
    "SignalPublisher",
    # market clock
    "TimeKeeper",
    "MarketClockProvider",
]
