"""Trade (tick) domain model.
Individual trade (tick) - for tick-level analysis.
Represents a single executed trade at a point in time.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType, MarketDataType
from tradingcz.sdk.registry import register_event, register_market_data


@register_event(EventType.TRADE)
@register_market_data(MarketDataType.TRADES)
class Trade(BaseModel):  # pylint: disable=too-many-instance-attributes
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(..., description="Trade timestamp, tz-aware UTC")
    price: float = Field(..., description="Trade execution price")
    size: float = Field(..., description="Trade size in shares")
    exchange: str | None = Field(default=None, description="Exchange code where trade occurred")
    trade_id: str | None = Field(default=None, description="Unique trade identifier")
    conditions: list[str] | None = Field(default=None, description="Trade conditions/modifiers")
