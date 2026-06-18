"""OrderClient — query order status.

Sends ServiceRequest to the event topic with ``service="get_orders"``
and awaits OrderList response.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events import ServiceRequestEvent

logger = logging.getLogger(__name__)


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
        logger.debug("OrderClient: get_orders status=%s symbol=%s", status, symbol)
        req = ServiceRequestEvent(
            service="get_orders",
            symbol=symbol,
            order_status=status,
        )
        resp = await self._rr.request(
            req,
            response_type=OrderList,
            timeout=timeout,
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


__all__ = ["OrderSummary", "OrderList", "OrderClient"]
