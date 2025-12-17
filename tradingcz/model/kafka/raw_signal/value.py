import enum
import pydantic
import typing


class SignalAction(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
    CLOSE = "CLOSE"


class SignalHorizon(str, enum.Enum):
    INTRA_1M = "INTRA_1M"
    INTRA_5M = "INTRA_5M"
    INTRA_15M = "INTRA_15M"
    SWING_D = "SWING_D"
    TREND_W = "TREND_W"



class SignalLogic(pydantic.BaseModel):
    """
    Core signal parameters
    """
    action: SignalAction = pydantic.Field(description="Signal direction: LONG, SHORT, FLAT, CLOSE")
    strength: float = pydantic.Field(description="Conviction level from 0.0 to 1.0")
    horizon: SignalHorizon = pydantic.Field(description="Expected holding period")



class Instrument(pydantic.BaseModel):
    """
    Instrument details
    """
    symbol: str = pydantic.Field(description="Ticker symbol (e.g., NVDA, MCD, BTC)")
    exchange: typing.Optional[str] = pydantic.Field(description="Exchange code (e.g., NASDAQ, CME)", default=None)
    currency: str = pydantic.Field(description="Currency code", default="USD")
    figi: typing.Optional[str] = pydantic.Field(description="OpenFIGI identifier for cross-provider mapping", default=None)



class RawSignalValue(pydantic.BaseModel):
    """
    Value for raw trading signal messages
    """
    signal_logic: SignalLogic
    instrument: Instrument
    metadata: typing.Optional[typing.Dict[str, str]] = pydantic.Field(description="Optional key-value metadata for debugging (current_price, ref_indicator, regime_detected)", default=None)

    
    class Meta:
        namespace = "cz.trading.model.kafka.raw_signal"
        field_order = ['signal_logic', 'metadata', 'instrument']

