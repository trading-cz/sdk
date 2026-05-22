"""Trading signal models and wire-format serialization.

Shared by all strategies so downstream consumers (risk, executor) receive
a consistent envelope regardless of which strategy produced a signal.
"""

from __future__ import annotations

import json
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


def build_signal(
    signal: TradingSignal,
    tracking_id: str,
    timestamp_utc_ms: int,
) -> bytes:
    """Serialize a TradingSignal to UTF-8 JSON bytes for the Kafka producer.

    The envelope uses a ``key`` / ``value`` split so Kafka consumers can route
    on the key without deserializing the full payload.

    Args:
        signal:            The strategy output to emit.
        tracking_id:       Run identifier for correlating signals across symbols.
        timestamp_utc_ms:  Emission timestamp in milliseconds since epoch (UTC).

    Returns:
        UTF-8 encoded JSON bytes.
    """
    payload = {
        "key": {
            "message_id": str(uuid.uuid4()),
            "tracking_id": tracking_id,
            "timestamp_utc_ms": timestamp_utc_ms,
            "strategy_id": signal.strategy_id,
            "schema_version": "1.0",
            "signal_type": "SIGNAL_EQUITY",
        },
        "value": {
            "symbol": signal.symbol,
            "side": signal.side,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "valid_until_et": signal.valid_until_et.isoformat(),
            "metadata": {
                "open_price": signal.open_price,
                "atr_period": signal.atr_period,
                "atr_value": signal.atr_value,
            },
        },
    }
    return json.dumps(payload, default=str).encode("utf-8")
