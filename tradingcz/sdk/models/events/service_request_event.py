"""Request  Event Model"""

from typing import Literal

from pydantic import Field

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events.base_event import BaseEvent


class ServiceRequestEvent(BaseEvent):
    """Service request order event model for any other request events
    except execution request events (request actual positions, cash, etc.)"""

    event_type: Literal[EventType.SERVICE_REQUEST] = Field(
        ...,
        description="Type of the event: execution_request or trading_signal",
    )
