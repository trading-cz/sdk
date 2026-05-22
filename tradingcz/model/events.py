"""Control-plane event models — messages on the shared events topic.

Wire protocol shared between ingestion service and strategy pods.
All models carry ``event_type`` as a literal discriminator for
Pydantic discriminated-union parsing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter


class DataRequest(BaseModel):
    """Request for historical or streaming market data."""

    event_type: Literal["data_request"] = "data_request"
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    source_app: str = ""
    type: Literal["historic", "stream", "unsubscribe"]
    asset: Literal["stock", "option", "crypto"] = "stock"
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

    event_type: Literal["data_ready"] = "data_ready"
    request_id: str
    broker: str
    data_topic: str
    type: Literal["historic", "stream"]
    bar_count: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DataError(BaseModel):
    """Error response to a DataRequest."""

    event_type: Literal["data_error"] = "data_error"
    request_id: str
    broker: str
    error: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- Discriminated union for parsing raw bytes ---

EventMessage = Annotated[
    DataRequest | DataReady | DataError,
    Field(discriminator="event_type"),
]

_event_adapter: TypeAdapter[DataRequest | DataReady | DataError] = TypeAdapter(
    EventMessage
)


def parse_event(raw: bytes) -> DataRequest | DataReady | DataError:
    """Deserialize raw JSON bytes into a typed event model."""
    return _event_adapter.validate_json(raw)
