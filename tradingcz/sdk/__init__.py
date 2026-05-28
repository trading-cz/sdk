"""SDK business layer — high-level API for trading applications.

Users import ``TradingApp``, call ``await app.start()`` (or use
``async with``), and use typed business methods like
``app.data.request_historical()``.

No Kafka knowledge required.
"""

from tradingcz.sdk._app import TradingApp

__all__ = ["TradingApp"]
