"""Pydantic domain models for ingestion data.

Frozen models with no vendor dependencies or I/O.
"""

from tradingcz.models.market.bar import Bar
from tradingcz.models.market.option_snapshot import OptionSnapshot
from tradingcz.models.market.quote import Quote
from tradingcz.models.market.snapshot import Snapshot
from tradingcz.models.market.stream_quote import StreamQuote
from tradingcz.models.market.trade import Trade

# Union of all market data types — use as the type parameter for TypedProducer
# when the channel carries heterogeneous market data (Trade, Bar, Quote, etc.).
# All members share ``symbol: str`` and ``timestamp: datetime``.
MarketItem = Trade | Bar | Quote | StreamQuote | Snapshot | OptionSnapshot

__all__ = [
    "Bar",
    "MarketItem",
    "OptionSnapshot",
    "Quote",
    "Trade",
    "Snapshot",
    "StreamQuote",
]
