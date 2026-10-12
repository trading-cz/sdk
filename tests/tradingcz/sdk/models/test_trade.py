"""Unit tests for the Trade model."""

from datetime import UTC, datetime
from types import SimpleNamespace

from tradingcz.sdk.models.market import Trade


def test_trade_id_accepts_alpaca_int_id_and_serializes_as_trade_id() -> None:
    alpaca_like = SimpleNamespace(symbol="SPY", timestamp=datetime(2026, 10, 12, tzinfo=UTC), price=500.0, size=10.0, exchange="V", id=52983525029461, conditions=["@"])

    trade = Trade.model_validate(alpaca_like, from_attributes=True)

    assert trade.trade_id == 52983525029461
    assert '"trade_id":52983525029461' in trade.model_dump_json()
    assert Trade.model_validate_json(trade.model_dump_json()) == trade
    assert Trade(symbol="SPY", timestamp=trade.timestamp, price=1.0, size=1.0, trade_id=7).trade_id == 7
