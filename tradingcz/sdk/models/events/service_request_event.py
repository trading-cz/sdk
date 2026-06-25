from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.registry import register_event


@register_event(EventType.SERVICE_REQUEST)
class ServiceRequestEvent(BaseModel):
    """General-purpose request to the executor/risk service.

    The ``service`` field names the operation (e.g. ``"get_balance"``,
    ``"get_orders"``, ``"get_positions"``).

    Correlation is handled by the transport layer — see
    :class:`~tradingcz.sdk.messaging.request_reply.RequestReply`.
    """

    event_id: UUID = Field(
        default_factory=uuid4, description="Unique identifier for the service request"
    )
    service: str = Field(..., description="Service operation name")
