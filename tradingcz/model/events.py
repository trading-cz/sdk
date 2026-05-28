"""Control-plane event models — messages on the shared event topic.

Wire protocol shared between ingestion service and strategy pods.

Message type is carried in the Kafka header ``message_type``, NOT in
the value payload.  The header tells the consumer which Pydantic model
to deserialize into.  This avoids self-typing fields in the value.

Message types:
    - ``"data_request"``  → DataRequest
    - ``"data_ready"``    → DataReady
    - ``"data_error"``    → DataError

All models carry ``request_id`` for correlation in request/reply flows.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class DataRequest(BaseModel):
    """Request for historical or streaming market data."""

    request_id: str = Field(default_factory=lambda: uuid4().hex)
    source_app: str = ""
    type: str = "historic"  # "historic", "stream", "unsubscribe"
    asset: str = "stock"  # "stock", "option", "crypto"
    broker: str = "alpaca"
    symbols: list[str]
    stream_type: str = "trades"
    timeframe: str = "1d"
    start_time: datetime | None = None
    end_time: datetime | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DataReady(BaseModel):
    """Acknowledgement: data is available on data_topic.

    Sent by ingestion after fulfilling a DataRequest.
    ``bar_count`` is set only when ``type="historic"``.
    """

    request_id: str
    broker: str
    data_topic: str
    type: str = "historic"  # "historic" or "stream"
    bar_count: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DataError(BaseModel):
    """Error response to a DataRequest."""

    request_id: str
    broker: str
    error: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ServiceRequest(BaseModel):
    """General-purpose request to the executor/risk service.

    Sent on the event topic with ``message_type = "service_request"``.
    The ``service`` field determines the expected response type.
    """

    request_id: str = Field(default_factory=lambda: uuid4().hex)
    source_app: str = ""
    service: str  # "get_positions", "get_balance", "get_orders", etc.
    symbol: str | None = None
    order_id: str | None = None
    order_status: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Message-type registry for header-based dispatch
# ---------------------------------------------------------------------------

_MESSAGE_TYPES: dict[str, type[BaseModel]] = {
    "data_request": DataRequest,
    "data_ready": DataReady,
    "data_error": DataError,
    "service_request": ServiceRequest,
}


def message_type_for(model: type[BaseModel]) -> str:
    """Return the ``message_type`` header value for a model class."""
    for mt, cls in _MESSAGE_TYPES.items():
        if cls is model:
            return mt
    raise KeyError(f"Unknown model type: {model.__name__}")


def parse_by_message_type(message_type: str, payload: bytes) -> BaseModel:
    """Deserialize JSON bytes into the correct model based on ``message_type`` header."""
    model_type = _MESSAGE_TYPES.get(message_type)
    if model_type is None:
        raise ValueError(f"Unknown message_type: {message_type}")
    return model_type.model_validate_json(payload)


# ---------------------------------------------------------------------------
# Deprecated: kept for backward compatibility with services on old SDK versions
# ---------------------------------------------------------------------------


def parse_event(raw: bytes) -> DataRequest | DataReady | DataError:
    """Deprecated.  Use ``parse_by_message_type(message_type, payload)`` instead.

    Tries each known event type until one parses successfully.
    """
    for model_type in [DataRequest, DataReady, DataError]:
        try:
            return model_type.model_validate_json(raw)  # type: ignore[return-value]
        except Exception:
            continue
    raise ValueError("Cannot parse event from bytes — unknown event type")
