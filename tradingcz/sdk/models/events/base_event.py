"""Base class for all events in the trading executor SDK."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType


class BaseEvent(BaseModel):
    """Base class for all events in the trading executor SDK. This class
    can be extended to include common fields or methods that are shared across different event types.
    """

    model_config = ConfigDict(frozen=True, use_enum_values=True)

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the event")
    received_at: datetime | None = Field(
        default_factory=lambda: datetime.now(UTC),  # pylint: disable=no-member
        description="Timestamp when the order request event was received",
    )
    event_type: EventType = Field(
        ...,
        description="Type of the event: execution_request or trading_signal",
    )
    # Optional fields for all events
    description: str | None = Field(
        default=None, description="Optional description of the order request"
    )
    parameters: dict | None = Field(
        default=None,
        description="Optional parameters for the order request",
    )
