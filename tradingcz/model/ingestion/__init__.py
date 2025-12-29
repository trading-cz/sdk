"""Pure domain models.

Lightweight dataclasses (slots=True, frozen=True) with no methods or vendor dependencies.
Serialization via tradingcz.model.serde, HTTP responses via tradingcz.model.response.
"""

from tradingcz.model.ingestion.bar import Bar
from tradingcz.model.ingestion.quote import Quote
from tradingcz.model.ingestion.snapshot import Snapshot
from tradingcz.model.ingestion.trade import Trade

__all__ = [
    "Bar",
    "Quote",
    "Trade",
    "Snapshot",
]
