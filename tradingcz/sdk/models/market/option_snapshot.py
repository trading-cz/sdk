"""Option snapshot domain model.

Combines latest trade, quote, and options-specific analytics (greeks,
implied volatility) in a single call.  More efficient than fetching
trade, quote, and greeks separately.
"""

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.models.market.quote import Quote
from tradingcz.sdk.models.market.trade import Trade


class OptionSnapshot(BaseModel):
    """Market snapshot for an option contract.

    Includes the latest trade, latest quote, implied volatility,
    and standard greeks.  All fields except ``symbol`` are optional
    because some providers may not return every field.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
