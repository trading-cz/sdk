"""Trade (tick) domain model.
Individual trade (tick) - for tick-level analysis.
Represents a single executed trade at a point in time.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Trade(BaseModel):  # pylint: disable=too-many-instance-attributes
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(..., description="Trade timestamp, tz-aware UTC")
    price: float = Field(..., description="Trade execution price")
    size: float = Field(..., description="Trade size in shares")
    exchange: str | None = Field(default=None, description="Exchange code where trade occurred")
    trade_id: str | None = Field(default=None, description="Unique trade identifier")
    conditions: list[str] | None = Field(default=None, description="Trade conditions/modifiers")
