"""PositionClient — query open positions.

Sends a ServiceRequestEvent (``ServiceRequestType.REQUEST_CURRENT_POSITIONS``)
to the event topic and awaits PositionList.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, EventType, ServiceRequestType
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
    """Response to a REQUEST_CURRENT_POSITIONS service request."""

    event_id: UUID = Field(..., description="Unique identifier for this event")
    positions: list[Position]


class PositionClient:
    """Query open positions via a ``REQUEST_CURRENT_POSITIONS`` service request."""

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(PositionList)

    async def get_positions(self, *, timeout: float = 30.0) -> list[Position]:
        """Return all currently open positions."""
        req = ServiceRequestEvent(service=ServiceRequestType.REQUEST_CURRENT_POSITIONS)
        resp = await self._rr.request(
            req,
            response_type=PositionList,
            event_id=str(req.event_id),  # executor replies with the payload event_id as header
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
