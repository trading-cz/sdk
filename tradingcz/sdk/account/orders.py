"""OrderClient — query order status.

Sends ServiceRequest to the event topic with ``service="get_orders"``
and awaits OrderList response.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.enums.order import (
    OrderClass,
    OrderSide,
    OrderStatus,
    TimeInForce,
)
from tradingcz.sdk.models.events import ServiceRequestEvent

logger = logging.getLogger(__name__)


class OrderSummary(BaseModel):
    """Full broker order response — shared across executor, simple-strategy, etc.

    Used both for query results (via OrderClient → OrderList) and as the
    individual order confirmation published by the executor after execution.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", use_enum_values=True)

    # ── Identity ──────────────────────────────────────────────────────
    id: UUID = Field(..., validation_alias=AliasChoices("client_order_id"))
    broker_order_id: UUID | None = Field(validation_alias=AliasChoices("id"), default=None)

    # ── Basic order fields ────────────────────────────────────────────
    order_status: OrderStatus | None = Field(validation_alias=AliasChoices("status"), default=None)
    symbol: str
    qty: Decimal | None = None
    notional: Decimal | None = None
    side: OrderSide | None = None
    time_in_force: TimeInForce | None = None
    order_class: OrderClass | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    # ── Fill info ─────────────────────────────────────────────────────
    filled_qty: Decimal | None = None
    filled_avg_price: Decimal | None = None

    # ── Timestamps ────────────────────────────────────────────────────
    created_at: datetime | None = None
    updated_at: datetime | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    expired_at: datetime | None = None
    expires_at: datetime | None = None
    canceled_at: datetime | None = None
    failed_at: datetime | None = None

    # ── Trailing stop ─────────────────────────────────────────────────
    trail_percent: Decimal | None = None
    trail_price: Decimal | None = None
    hwm: Decimal | None = None

    # ── Nested legs (bracket/OTO/OCO) ─────────────────────────────────
    legs: list["OrderSummary"] | None = None


class OrderResponse(BaseModel):
    """Single order confirmation — published by executor after execution."""

    event_id: str
    order: OrderSummary


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


__all__ = ["OrderSummary", "OrderResponse", "OrderList", "OrderClient"]
