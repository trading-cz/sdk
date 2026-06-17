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

All models carry ``event_id`` for correlation in request/reply flows.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.event import DataRequestType
from tradingcz.sdk.models.enums.timeframe import Timeframe


# TODO:
class DataRequest(BaseModel):
    """Request for historical or streaming market data.
    """

    event_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the order")
    type: DataRequestType
    asset: str = "stock"  # "stock", "option", "crypto"
    broker: str = "alpaca"
    symbols: list[str]
    historical_data_type: str = "bars"  # "bars" | "trades" | "quotes" | "snapshots"
    stream_type: str = "trades"
    timeframe: Timeframe = Timeframe.D1  # canonical format: "1d", "4h", etc.
    start_time: datetime | None = None
    end_time: datetime | None = None


class DataReady(BaseModel):
    """Acknowledgement: data is available on data_topic.

    Sent by ingestion after fulfilling a DataRequest.
    ``record_count`` is set only when ``type="historic"``.
    """

    event_id: str
    broker: str
    data_topic: str
    type: str = "historic"  # "historic" or "stream"
    record_count: int | None = None


class DataError(BaseModel):
    """Error response to a DataRequest."""

    event_id: str
    broker: str
    error: str