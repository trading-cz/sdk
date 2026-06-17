from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from tradingcz.sdk.models.enums.event import OrderRequest, StrategyType


class ExecutionRequestEvent(BaseModel):
    """Represents an execution & strategy request event received
    """

    event_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the order")
    strategy_type: StrategyType = Field(..., description="Type of the strategy that generated the order request")
    orders: list[OrderRequest] = Field(..., description="List of market orders in the order request")
