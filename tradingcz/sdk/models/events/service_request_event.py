from pydantic import BaseModel, Field
from uuid import UUID, uuid4


# TODO: nedodelano, nutno predelat, nepouzivat
class ServiceRequestEvent(BaseModel):
    """General-purpose request to the executor/risk service.
    """

    event_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the order")
    service: str  # "get_positions", "get_balance"..
    symbol: str | None = None
    order_id: str | None = None
    order_status: str | None = None


# 1 -> jak to je v DB
# 2 -> jak to je na brokeru


# ucet -> $$$
# pozice - open, executed