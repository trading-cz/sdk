import datetime
import enum
import pydantic
import uuid


class SignalType(str, enum.Enum):
    SIGNAL_EQUITY = "SIGNAL_EQUITY"
    SIGNAL_FUTURE = "SIGNAL_FUTURE"
    SIGNAL_OPTION = "SIGNAL_OPTION"
    SIGNAL_CRYPTO = "SIGNAL_CRYPTO"
    SIGNAL_FX = "SIGNAL_FX"



class RawSignalKey(pydantic.BaseModel):
    """
    Key for raw trading signal messages
    """
    message_id: uuid.UUID = pydantic.Field(description="UUID v4: Unique identifier for this message")
    tracking_id: str = pydantic.Field(description="Correlation ID that travels with the trade (e.g., run-20231027-A)")
    timestamp_utc: datetime.datetime = pydantic.Field(description="Precise generation time in UTC as epoch milliseconds")
    strategy_id: str = pydantic.Field(description="Source strategy identifier (e.g., strategy_worker_trend_01)")
    schema_id: str = pydantic.Field(description="Schema version string (e.g., 1.2)")
    signal_type: SignalType = pydantic.Field(description="Asset class of the signal")

    
    class Meta:
        namespace = "cz.trading.model.kafka.raw_signal"

