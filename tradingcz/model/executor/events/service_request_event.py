"""Request  Event Model"""

from typing import Literal

from tradingcz.model.enum.event import EventType
from tradingcz.model.executor.events.base_event import BaseEvent


class ServiceRequestEvent(BaseEvent):
    """Service request order event model for any other request events
    except execution request events (request actual positions, cash, etc.)"""

    event_type: Literal[EventType.SERVICE_REQUEST]
