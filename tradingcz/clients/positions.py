"""PositionClient — query open positions via the event topic."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from tradingcz.models.headers import MessageType
from tradingcz.framework.helpers import RequestReply


class Position(BaseModel):
    """A single open position."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    avg_entry_price: float
    asset_type: Literal["stock", "option"] = "stock"


class PositionList(BaseModel):
    """Response to a get_positions request."""

    request_id: str
    positions: list[Position]


class PositionClient:
    """Query open positions.

    Sends ServiceRequest to the event topic with ``service="get_positions"``
    and awaits PositionList response.
    """

    def __init__(self, rr: RequestReply) -> None:
        self._rr = rr
        self._rr.register_type(MessageType.POSITION_RESPONSE, PositionList)

    async def get_positions(self, *, timeout: float = 30.0) -> list[Position]:
        """Return all currently open positions."""
        from tradingcz.models.events import ServiceRequest

        req = ServiceRequest(service="get_positions")
        resp = await self._rr.request(req, response_type=PositionList, timeout=timeout)
        return resp.positions

    async def get_position(self, symbol: str, *, timeout: float = 30.0) -> Position | None:
        """Return position for a single symbol, or None."""
        positions = await self.get_positions(timeout=timeout)
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None
