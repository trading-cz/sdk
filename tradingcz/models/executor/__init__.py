"""Pure domain models.

Lightweight dataclasses (slots=True, frozen=True) with no methods or vendor dependencies.
Serialization via tradingcz.model.serde, HTTP responses via tradingcz.model.response.
"""

from tradingcz.models.executor.orders.single_market_orders.limit_order import (
    LimitOrderRequest,
)
from tradingcz.models.executor.orders.single_market_orders.market_order import (
    MarketOrderRequest,
)

__all__ = ["LimitOrderRequest", "MarketOrderRequest"]
