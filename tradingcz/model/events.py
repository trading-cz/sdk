"""Control-plane event models — messages on the shared event topic.

Wire protocol shared between ingestion, executor, and strategy pods.

Message type is carried in the Kafka header ``message_type``, NOT in
the value payload.  Use ``tradingcz.model.headers.parse_message()``
to deserialize based on the header.

Models:
    - ``DataRequest``  — request historical or streaming market data
    - ``DataReady``    — acknowledgement: data available on data_topic
    - ``DataError``    — error response to a DataRequest
    - ``ServiceRequest`` — general-purpose request to executor/risk

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



