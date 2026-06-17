"""tradingcz.sdk — SDK library for trading-cz platform.

Core building blocks for all trading-cz services:
- transport, messaging, serialization
- models (market data, events, orders)
- trading clients, indicators, common utilities
"""

from pathlib import Path
from pkgutil import extend_path

from tradingcz.sdk.trading import TradingApp, ServiceApp

__all__ = ["TradingApp", "ServiceApp"]

# Allow `tradingcz.sdk.*` portions from multiple distributions.
__path__ = extend_path(__path__, __name__)

_generated = Path(__file__).resolve().parents[2] / "generated" / "tradingcz" / "sdk"
if _generated.is_dir():
    __path__.append(str(_generated))
