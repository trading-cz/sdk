"""tradingcz.sdk.trading — market data and account clients for strategies.

The primary entry point for strategy developers::

    from tradingcz.sdk.trading import TradingApp

    async with TradingApp(service_id="my-strategy") as app:
        bars = await app.stock.bars(["AAPL"], days=30)
        await app.signals.publish(signal, event_id="...")
"""

from tradingcz.sdk.trading.service import ServiceApp
from tradingcz.sdk.trading.app import TradingApp
from tradingcz.sdk.trading.account import BalanceClient, OrderClient, PositionClient
from tradingcz.sdk.trading.corporate import CorporateActionsClient
from tradingcz.sdk.trading.options import OptionsDataClient
from tradingcz.sdk.trading.signals import SignalPublisher
from tradingcz.sdk.trading.stock import StockDataClient
from tradingcz.sdk.trading.time_keeper import MarketClockProvider, TimeKeeper

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
    # signal publishing
    "SignalPublisher",
    # market clock
    "TimeKeeper",
    "MarketClockProvider",
]
