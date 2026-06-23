from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.event import EventType, OrderRequest, StrategyType
from tradingcz.sdk.registry import register_event


@register_event(EventType.EXECUTION_REQUEST)
class ExecutionRequestEvent(BaseModel):
    """Represents an execution & strategy request event received.

    Correlation is handled by the transport layer — see
    :class:`~tradingcz.sdk.messaging.request_reply.RequestReply`.
    """

    strategy_type: StrategyType = Field(..., description="Type of strategy that generated this request")
    orders: list[OrderRequest] = Field(..., description="List of orders to execute")
