"""BalanceClient — query account balance.

Sends ServiceRequest to the event topic with ``service="get_balance"``
and awaits BalanceResponse.
"""

from __future__ import annotations

import logging
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events import ServiceRequestEvent
from tradingcz.sdk.registry import register_event

logger = logging.getLogger(__name__)


class Balance(BaseModel):
    """Account balance snapshot."""

    model_config = ConfigDict(frozen=True)

    cash: float
    buying_power: float
    portfolio_value: float = 0.0
    currency: str = "USD"


@register_event(EventType.BALANCE_RESPONSE)
class BalanceResponse(BaseModel):
    """Response to a balance query."""

    event_id: UUID = Field(..., description="Unique identifier for this event")
    balance: Balance


class BalanceClient:
    """Query account balance.

    Sends ServiceRequest to the event topic with ``service="get_balance"``
    and awaits BalanceResponse.
    """

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(BalanceResponse)

    async def get_balance(self, *, timeout: float = 30.0) -> Balance:
        """Return current account balance."""
        logger.debug("BalanceClient: get_balance")
        req = ServiceRequestEvent(service="get_balance")
        resp = await self._rr.request(
            req,
            response_type=BalanceResponse,
            timeout=timeout,
        )
        return resp.balance

    async def get_buying_power(self, *, timeout: float = 30.0) -> float:
        """Return available buying power (convenience)."""
        balance = await self.get_balance(timeout=timeout)
        return balance.buying_power


__all__ = ["Balance", "BalanceResponse", "BalanceClient"]
