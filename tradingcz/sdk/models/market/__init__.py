"""Pydantic domain models for ingestion data.

Frozen models with no vendor dependencies or I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingcz.sdk.models.enums.event import EventType

from tradingcz.sdk.models.market.bar import Bar
from tradingcz.sdk.models.market.corporate import Dividend, StockSplit
from tradingcz.sdk.models.market.option_snapshot import OptionSnapshot
from tradingcz.sdk.models.market.quote import Quote
from tradingcz.sdk.models.market.snapshot import Snapshot
from tradingcz.sdk.models.market.trade import Trade
from tradingcz.sdk.registry import EventRegistry

# Union of all market data types — use as the type parameter for TypedProducer
# when the channel carries heterogeneous market data (Trade, Bar, Quote, etc.).
# All members share ``symbol: str`` and ``timestamp: datetime``.
MarketItem = Trade | Bar | Quote | Snapshot | OptionSnapshot


def market_item_message_type(item: MarketItem) -> EventType:
    """Infer the ``EventType`` from a market data item via EventRegistry.

    .. deprecated::
        Use ``EventRegistry.event_type_for(item)`` directly.
        This shim exists for backward compatibility.

    Example::

        >>> market_item_message_type(Bar(...))       # → EventType.BAR
        >>> market_item_message_type(Trade(...))     # → EventType.TRADE
        >>> market_item_message_type(Quote(...))     # → EventType.QUOTE
    """
    return EventRegistry.event_type_for(item)


__all__ = [
    "Bar",
    "Dividend",
    "MarketItem",
    "market_item_message_type",
    "OptionSnapshot",
    "Quote",
    "StockSplit",
    "Trade",
    "Snapshot",
]
