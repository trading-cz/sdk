"""Account state clients — balance, orders, positions.

All three query the executor service via the event topic using
request/reply.  No Kafka knowledge required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.transport.exchange import RequestReply
from tradingcz.sdk.models.enums.event import EventType


# ═════════════════════════════════════════════════════════════════════════════
# BalanceClient
# ═════════════════════════════════════════════════════════════════════════════


# TODO: Petr
class Balance(BaseModel):
    """Account balance snapshot."""

    model_config = ConfigDict(frozen=True)

    cash: float
    buying_power: float
    portfolio_value: float = 0.0
    currency: str = "USD"


class BalanceResponse(BaseModel):
    """Response to a balance query."""

    event_id: str
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
        from tradingcz.sdk.models.events import ServiceRequestEvent

        req = ServiceRequestEvent(service="get_balance")
        resp = await self._rr.request(
            req, response_type=BalanceResponse, timeout=timeout,
            request_type=EventType.SERVICE_REQUEST,
        )
        return resp.balance

    async def get_buying_power(self, *, timeout: float = 30.0) -> float:
        """Return available buying power (convenience)."""
        balance = await self.get_balance(timeout=timeout)
        return balance.buying_power


# ═════════════════════════════════════════════════════════════════════════════
# OrderClient
# ═════════════════════════════════════════════════════════════════════════════


# TODO: Petr
class OrderSummary(BaseModel):
    """Summary of a single order."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    filled_qty: float = 0.0
    created_at: datetime | None = None


class OrderList(BaseModel):
    """Response to a get_orders request."""

    event_id: str
    orders: list[OrderSummary]


class OrderClient:
    """Query order status.

    Sends ServiceRequest to the event topic with ``service="get_orders"``
    and awaits OrderList response.
    """

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(EventType.ORDER_RESPONSE, OrderList)

    async def get_orders(
        self,
        *,
        status: str | None = None,
        symbol: str | None = None,
        timeout: float = 30.0,
    ) -> list[OrderSummary]:
        """Return orders, optionally filtered."""
        from tradingcz.sdk.models.events import ServiceRequestEvent

        req = ServiceRequestEvent(
            service="get_orders",
            symbol=symbol,
            order_status=status,
        )
        resp = await self._rr.request(
            req, response_type=OrderList, timeout=timeout,
            request_type=EventType.SERVICE_REQUEST,
        )
        return resp.orders

    async def get_order_status(
        self, order_id: str, *, timeout: float = 30.0
    ) -> OrderSummary | None:
        """Return a single order by ID, or None."""
        orders = await self.get_orders(timeout=timeout)
        for o in orders:
            if o.order_id == order_id:
                return o
        return None


# ═════════════════════════════════════════════════════════════════════════════
# PositionClient
# ═════════════════════════════════════════════════════════════════════════════


# TODO: Petr
class Position(BaseModel):
    """A single open position."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    avg_entry_price: float
    asset_type: Literal["stock", "option"] = "stock"


class PositionList(BaseModel):
    """Response to a get_positions request."""

    event_id: str
    positions: list[Position]


class PositionClient:
    """Query open positions.

    Sends ServiceRequest to the event topic with ``service="get_positions"``
    and awaits PositionList response.
    """

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(EventType.POSITION_RESPONSE, PositionList)

    async def get_positions(self, *, timeout: float = 30.0) -> list[Position]:
        """Return all currently open positions."""
        from tradingcz.sdk.models.events import ServiceRequestEvent

        req = ServiceRequestEvent(service="get_positions")
        resp = await self._rr.request(
            req, response_type=PositionList, timeout=timeout,
            request_type=EventType.SERVICE_REQUEST,
        )
        return resp.positions

    async def get_position(self, symbol: str, *, timeout: float = 30.0) -> Position | None:
        """Return position for a single symbol, or None."""
        positions = await self.get_positions(timeout=timeout)
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None
