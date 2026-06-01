"""Module containing the OrderRequestEvent model, which represents a market order request event received via generic listener."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from tradingcz.model.enum.event import EventType, StrategyType
from tradingcz.model.executor.events.base_event import BaseEvent
from tradingcz.model.executor.events.single_order_request import SingleOrderRequest


class ExecutionRequestEvent(BaseEvent):
    """Represents an execution request event received via generic listener.
    Basic and immutable recipe for ExecutionRequestEvent model, with static field values, frozen."""

    id: UUID = Field(..., description="Unique identifier for the event")
    strategy_type: StrategyType = Field(
        default=StrategyType.SINGLE_ORDER,
        description="Type of the strategy that generated the order request",
    )
    event_type: Literal[EventType.EXECUTION_REQUEST]
    market_orders: list[SingleOrderRequest] = Field(
        ..., description="List of market orders in the order request"
    )
