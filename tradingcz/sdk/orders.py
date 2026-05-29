"""OrderClient — query order status via the event topic."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.model.headers import MessageType
from tradingcz.sdk._helpers import _RequestReply


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

    request_id: str
    orders: list[OrderSummary]


class OrderClient:
    """Query order status.

    Sends ServiceRequest to the event topic with ``service="get_orders"``
    and awaits OrderList response.
    """

    def __init__(self, rr: _RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(MessageType.ORDER_RESPONSE, OrderList)

    async def get_orders(
        self,
        *,
        status: str | None = None,
        symbol: str | None = None,
        timeout: float = 30.0,
    ) -> list[OrderSummary]:
        """Return orders, optionally filtered."""
        from tradingcz.model.events import ServiceRequest

        req = ServiceRequest(
            service="get_orders",
            symbol=symbol,
            order_status=status,
        )
        resp = await self._rr.request(req, response_type=OrderList, timeout=timeout)
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
