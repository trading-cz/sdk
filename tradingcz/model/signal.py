"""Trading signal models and wire-format serialization.

Shared by all strategies so downstream consumers (risk, executor) receive
a consistent envelope regardless of which strategy produced a signal.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TradingSignal(BaseModel):
    """Strategy output — direction + levels, intentionally without position size.

    Designed to be close to the executor's ExecutionRequestEvent so that a risk
    application can translate it by simply adding ``qty`` and ``order_class``.
    """

    symbol: str
    side: Literal["LONG", "SHORT"]
    strategy_id: str = Field(default="")
    open_price: float
    entry_price: float
    stop_loss: float
    valid_until_et: datetime
    atr_period: int = 3
    atr_value: float


# ---------------------------------------------------------------------------
# Wire-format envelope (key / value split for Kafka routing)
# ---------------------------------------------------------------------------


class SignalMetadata(BaseModel):
    """Strategy-level metadata carried alongside the signal value."""

    open_price: float
    atr_period: int = 3
    atr_value: float


class SignalValue(BaseModel):
    """Trade-relevant portion of a signal (symbol, side, levels)."""

    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_price: float
    stop_loss: float
    valid_until_et: datetime
    metadata: SignalMetadata


class SignalKey(BaseModel):
    """Kafka message key for signal routing and correlation."""

    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tracking_id: str
    timestamp_utc_ms: int
    strategy_id: str = ""
    schema_version: str = "1.0"
    signal_type: str = "SIGNAL_EQUITY"


class SignalEnvelope(BaseModel):
    """Full Kafka message envelope: key (routing) + value (signal payload).

    Downstream consumers (risk, executor) deserialize this envelope to
    route on the key and act on the value.
    """

    key: SignalKey
    value: SignalValue


def build_signal(
    signal: TradingSignal,
    tracking_id: str,
    timestamp_utc_ms: int,
) -> bytes:
    """Serialize a TradingSignal to UTF-8 JSON bytes for the Kafka producer.

    Constructs a ``SignalEnvelope`` with key/value split so Kafka consumers can
    route on the key without deserializing the full payload.

    Args:
        signal:            The strategy output to emit.
        tracking_id:       Run identifier for correlating signals across symbols.
        timestamp_utc_ms:  Emission timestamp in milliseconds since epoch (UTC).

    Returns:
        UTF-8 encoded JSON bytes.
    """
    envelope = SignalEnvelope(
        key=SignalKey(
            tracking_id=tracking_id,
            timestamp_utc_ms=timestamp_utc_ms,
            strategy_id=signal.strategy_id,
        ),
        value=SignalValue(
            symbol=signal.symbol,
            side=signal.side,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            valid_until_et=signal.valid_until_et,
            metadata=SignalMetadata(
                open_price=signal.open_price,
                atr_period=signal.atr_period,
                atr_value=signal.atr_value,
            ),
        ),
    )
    return envelope.model_dump_json().encode()
