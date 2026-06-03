"""Pure domain models.

Lightweight dataclasses (slots=True, frozen=True) with no methods or vendor dependencies.
Serialization via tradingcz.model.serde, HTTP responses via tradingcz.model.response.
"""

from tradingcz.models.executor.limit_order import LimitOrder
from tradingcz.models.executor.market_order import MarketOrder

__all__ = ["LimitOrder", "MarketOrder"]
