"""PositionClient — query open positions.

Sends ServiceRequest to the event topic with ``service="get_positions"``
and awaits PositionList response.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, EventType
from tradingcz.sdk.models.events import ServiceRequestEvent
from tradingcz.sdk.registry import register_event


class Position(BaseModel):
    """A single open position."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    avg_entry_price: float
    asset_type: AssetType = AssetType.STOCK


@register_event(EventType.POSITION_RESPONSE)
class PositionList(BaseModel):
    """Response to a get_positions request."""

    event_id: UUID = Field(..., description="Unique identifier for this event")
    positions: list[Position]


class PositionClient:
    """Query open positions.

    Sends ServiceRequest to the event topic with ``service="get_positions"``
    and awaits PositionList response.
    """

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(PositionList)

    async def get_positions(self, *, timeout: float = 30.0) -> list[Position]:
        """Return all currently open positions."""
        req = ServiceRequestEvent(service="get_positions")
        resp = await self._rr.request(
            req,
            response_type=PositionList,
            timeout=timeout,
        )
        return resp.positions

    async def get_position(self, symbol: str, *, timeout: float = 30.0) -> Position | None:
        """Return position for a single symbol, or None."""
        positions = await self.get_positions(timeout=timeout)
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None


__all__ = ["Position", "PositionList", "PositionClient"]
