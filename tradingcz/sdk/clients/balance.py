"""BalanceClient — query account balance via the event topic."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.framework.helpers import RequestReply
from tradingcz.sdk.models.enums.event import EventType


class Balance(BaseModel):
    """Account balance snapshot."""

    model_config = ConfigDict(frozen=True)

    cash: float
    buying_power: float
    portfolio_value: float = 0.0
    currency: str = "USD"


class BalanceResponse(BaseModel):
    """Response to a balance query."""

    request_id: str
    balance: Balance


class BalanceClient:
    """Query account balance.

    Sends ServiceRequest to the event topic with ``service="get_balance"``
    and awaits BalanceResponse.
    """

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(EventType.BALANCE_RESPONSE, BalanceResponse)

    async def get_balance(self, *, timeout: float = 30.0) -> Balance:
        """Return current account balance."""
        from tradingcz.sdk.models.events import ServiceRequest

        req = ServiceRequest(service="get_balance")
        resp = await self._rr.request(
            req, response_type=BalanceResponse, timeout=timeout
        )
        return resp.balance

    async def get_buying_power(self, *, timeout: float = 30.0) -> float:
        """Return available buying power (convenience)."""
        balance = await self.get_balance(timeout=timeout)
        return balance.buying_power
