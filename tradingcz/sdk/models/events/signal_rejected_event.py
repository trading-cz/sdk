"""SignalRejectedEvent — published by risk service when a trading signal is rejected.

Sent to the events topic so downstream consumers (monitoring, strategies)
can react to the rejection.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.registry import register_event


@register_event(EventType.SIGNAL_REJECTED)
class SignalRejectedEvent(BaseModel):
    """Published by the risk service when a trading signal fails risk checks.

    ``event_id`` is copied from the original :class:`TradingSignalEvent` so the
    rejection can be correlated back to the signal without a separate field.

    Attributes:
        event_id: Copied from the original ``TradingSignalEvent.event_id``.
        symbol: Ticker symbol the signal was for.
        reason: Machine-readable rejection code (e.g. ``slot_conflict``,
            ``risk_limit_exceeded``, ``zero_quantity``).
        detail: Human-readable explanation for logs and monitoring.
    """

    event_id: UUID
    symbol: str
    reason: str
    detail: str = ""
