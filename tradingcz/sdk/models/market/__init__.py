"""Pydantic domain models for ingestion data.

Frozen models with no vendor dependencies or I/O.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingcz.sdk.models.enums.event import EventType

from tradingcz.sdk.models.market.bar import Bar
from tradingcz.sdk.models.market.option_snapshot import OptionSnapshot
from tradingcz.sdk.models.market.quote import Quote
from tradingcz.sdk.models.market.snapshot import Snapshot
from tradingcz.sdk.models.market.stream_quote import StreamQuote
from tradingcz.sdk.models.market.trade import Trade

# Union of all market data types — use as the type parameter for TypedProducer
# when the channel carries heterogeneous market data (Trade, Bar, Quote, etc.).
# All members share ``symbol: str`` and ``timestamp: datetime``.
MarketItem = Trade | Bar | Quote | StreamQuote | Snapshot | OptionSnapshot

# TODO SMAZAT
def market_item_message_type(item: MarketItem) -> EventType:
    """Infer the ``EventType`` from a market data item's class name.

    Converts CamelCase class name to snake_case and looks up the
    corresponding ``EventType`` enum member.  For example::

        >>> market_item_message_type(Bar(...))       # → EventType.BAR
        >>> market_item_message_type(Trade(...))     # → EventType.TRADE
        >>> market_item_message_type(StreamQuote(...))  # → EventType.STREAM_QUOTE

    This is the canonical mapping for all market data types.
    Apps should use this instead of manually computing the
    CamelCase → snake_case → EventType chain.
    """
    # Deferred import to avoid circular dependency at module level
    from tradingcz.sdk.models.enums.event import (
        EventType as _MT,  # pylint: disable=import-outside-toplevel
    )

    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", type(item).__name__).lower()
    return _MT(snake)


__all__ = [
    "Bar",
    "MarketItem",
    "market_item_message_type",
    "OptionSnapshot",
    "Quote",
    "Trade",
    "Snapshot",
    "StreamQuote",
]
