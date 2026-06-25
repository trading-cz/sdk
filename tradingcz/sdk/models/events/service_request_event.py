from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.event import ServiceRequestType


class ServiceRequestEvent(BaseModel):
    """General-purpose request to the executor/risk service.

    Carries ``event_id`` for request/reply correlation.  The ``service``
    field names the operation (e.g. ``"get_balance"``, ``"get_orders"``,
    ``"get_positions"``).
    """

    event_id: UUID = Field(
        default_factory=uuid4, description="Unique identifier for the service request"
    )
    service: ServiceRequestType = Field(..., description="Service operation name")
