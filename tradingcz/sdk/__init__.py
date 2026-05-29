"""SDK business layer — high-level API for trading applications.

Two entry points:
  - ``TradingApp``  — strategy/consumer role (data, signals, positions)
  - ``ServiceApp``  — base class for ALL services (transport, health, shutdown)

Utilities:
  - ``Retry``       — generic async retry wrapper for any operation

No Kafka knowledge required.
"""

from tradingcz.sdk._app import TradingApp
from tradingcz.sdk._service import ServiceApp
from tradingcz.sdk.retry import Retry

__all__ = ["TradingApp", "ServiceApp", "Retry"]
