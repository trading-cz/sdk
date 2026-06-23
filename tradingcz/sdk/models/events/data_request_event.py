"""Control-plane event models — messages on the shared event topic.

Wire protocol shared between ingestion, executor, and strategy pods.

Message type is carried in the Kafka header ``message_type``, NOT in
the value payload.  Use ``tradingcz.model.headers.parse_message()``
to deserialize based on the header.

Models:
    - ``DataRequest``  — request historical or streaming market data
    - ``DataReady``    — acknowledgement: data available on data_topic
    - ``DataError``    — error response to a DataRequest

All models carry ``event_id`` for correlation in request/reply flows.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.event import (
    AssetType,
    Broker,
    DataRequestType,
    EventType,
    MarketDataType,
)
from tradingcz.sdk.models.enums.timeframe import Timeframe
from tradingcz.sdk.registry import register_event


@register_event(EventType.DATA_REQUEST)
class DataRequest(BaseModel):
    """Request for historical or streaming market data.
    """

    event_id: UUID = Field(default_factory=uuid4, description="Unique identifier for data request")
    type: DataRequestType = Field(..., description="Request type: historical or streaming")
    source_app: str = Field(default="", description="Service identity of the requester (set by transport layer)")
    asset: AssetType = Field(default=AssetType.STOCK, description="Asset class: stock, option, etc.")
    broker: Broker | None = Field(default=Broker.ALPACA, description="Data provider broker")
    symbols: list[str] = Field(..., description="List of ticker symbols to request")
    data_type: MarketDataType = Field(default=MarketDataType.BARS, description="Data type: bars, quotes, trades")
    timeframe: Timeframe = Field(default=Timeframe.D1, description="Candle timeframe (1d, 4h, etc.)")
    start_time: datetime | None = Field(default=None, description="Start time for historical data; omit both start_time+end_time for latest-only")
    end_time: datetime | None = Field(default=None, description="End time for historical data; omit both start_time+end_time for latest-only")


@register_event(EventType.DATA_READY)
class DataReady(BaseModel):
    """Acknowledgement: data is available on data_topic.

    Sent by ingestion after fulfilling a DataRequest.
    ``record_count`` is set only when ``type=DataRequestType.HISTORIC``.
    """

    event_id: str = Field(..., description="Correlation ID from DataRequest")
    broker: Broker = Field(..., description="Data provider broker")
    data_topic: str = Field(..., description="Kafka topic where data is published")
    type: DataRequestType = Field(default=DataRequestType.HISTORIC, description="Request type: historical or streaming")
    record_count: int | None = Field(default=None, description="Number of records published (historic only)")


@register_event(EventType.DATA_ERROR)
class DataError(BaseModel):
    """Error response to a DataRequest."""

    event_id: str = Field(..., description="Correlation ID from DataRequest")
    broker: Broker = Field(..., description="Data provider broker")
    error: str = Field(..., description="Error message describing the failure")
