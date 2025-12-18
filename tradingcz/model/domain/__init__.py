"""Pure domain models.

Lightweight dataclasses (slots=True, frozen=True) with no methods or vendor dependencies.
Serialization via tradingcz.model.serde, HTTP responses via tradingcz.model.response.
"""

from .bar import Bar
from .quote import Quote
from .trade import Trade
from .snapshot import Snapshot

__all__ = [
    "Bar",
    "Quote",
    "Trade",
    "Snapshot",
]
