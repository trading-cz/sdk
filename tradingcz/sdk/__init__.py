"""SDK business layer — high-level API for trading applications.

Two entry points:
  - ``TradingApp``  — strategy/consumer role (data, signals, positions)
  - ``ServiceApp``  — base class for ALL services (transport, health, shutdown)

No Kafka knowledge required.
"""

from tradingcz.sdk._app import TradingApp
from tradingcz.sdk._service import ServiceApp

__all__ = ["TradingApp", "ServiceApp"]
