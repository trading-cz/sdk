"""Module containing the OrderRequestEvent model, which represents a market order request event received via generic listener."""

from pydantic import Field

from tradingcz.sdk.models.enums.event import EventType, OrderRequest, StrategyType
from tradingcz.sdk.models.events.base_event import BaseEvent


class ExecutionRequestEvent(BaseEvent):
    """Represents an execution request event received via generic listener.
    Basic and immutable recipe for ExecutionRequestEvent model, with static field values, frozen.
    """

    strategy_type: StrategyType = Field(
        ...,
        description="Type of the strategy that generated the order request",
    )
    event_type: EventType = Field(
        default=EventType.EXECUTION_REQUEST,
        description="Type of the event: execution_request or trading_signal",
    )
    orders: list[OrderRequest] = Field(
        ..., description="List of market orders in the order request"
    )
