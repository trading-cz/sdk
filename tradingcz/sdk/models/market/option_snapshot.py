"""Option snapshot domain model.

Combines latest trade, quote, and options-specific analytics (greeks,
implied volatility) in a single call.  More efficient than fetching
trade, quote, and greeks separately.
"""

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.market.quote import Quote
from tradingcz.sdk.models.market.trade import Trade
from tradingcz.sdk.registry import register_event


@register_event(EventType.OPTION_SNAPSHOT)
class OptionSnapshot(BaseModel):
    """Market snapshot for an option contract.

    Includes the latest trade, latest quote, implied volatility,
    and standard greeks.  All fields except ``symbol`` are optional
    because some providers may not return every field.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Option contract symbol")
    latest_trade: Trade | None = Field(default=None, description="Latest executed trade")
    latest_quote: Quote | None = Field(default=None, description="Latest bid/ask quote")
    implied_volatility: float | None = Field(default=None, description="Implied volatility percentage")
    delta: float | None = Field(default=None, description="Delta greek - price sensitivity")
    gamma: float | None = Field(default=None, description="Gamma greek - delta sensitivity")
    theta: float | None = Field(default=None, description="Theta greek - time decay")
    vega: float | None = Field(default=None, description="Vega greek - volatility sensitivity")
    rho: float | None = Field(default=None, description="Rho greek - interest rate sensitivity")
