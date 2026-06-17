"""EventType → Pydantic model dispatch for deserialization.

Simple, explicit mapping — no lazy init, no function-imports, no global mutation.
"""

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events import (
    DataError,
    DataReady,
    DataRequest,
    ServiceRequestEvent,
)
from tradingcz.sdk.models.events.execution_request_event import ExecutionRequestEvent
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.models.market import Bar, Quote, Snapshot, StreamQuote, Trade

# ── EventType → Pydantic model mapping ──────────────────────────────────────

_MODEL: dict[str, type[BaseModel]] = {
    EventType.DATA_REQUEST: DataRequest,
    EventType.DATA_READY: DataReady,
    EventType.DATA_ERROR: DataError,
    EventType.SERVICE_REQUEST: ServiceRequestEvent,
    EventType.SERVICE_LIFECYCLE: LifecycleEvent,
    EventType.TRADING_SIGNAL: ExecutionRequestEvent,
    EventType.EXECUTION_REQUEST: ExecutionRequestEvent,
    EventType.BAR: Bar,
    EventType.QUOTE: Quote,
    EventType.TRADE: Trade,
    EventType.STREAM_QUOTE: StreamQuote,
    EventType.SNAPSHOT: Snapshot,
}


def model_for(event_type: EventType) -> type[BaseModel]:
    """Return the Pydantic model class for an EventType value.

    Raises ``ValueError`` if unknown.
    """
    key = str(event_type)
    try:
        return _MODEL[key]
    except KeyError:
        raise ValueError(f"Unknown event type: {key!r}") from None


def parse_message(event_type: str | EventType, payload: bytes) -> BaseModel:
    """Deserialize a Kafka message payload into its typed model.

    Example::

        model = parse_message(msg.headers["event_type"], msg.payload)
    """
    return model_for(event_type).model_validate_json(payload)
