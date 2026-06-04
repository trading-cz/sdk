"""Unit tests for tradingcz.model.signal.TradingSignal."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tradingcz.models.signal import TradingSignal


class TestTradingSignal:
    """Tests for TradingSignal model."""

    def test_valid_long_signal(self) -> None:
        s = TradingSignal(
            symbol="AAPL",
            side="LONG",
            strategy_id="test-strat",
            open_price=150.0,
            entry_price=151.0,
            stop_loss=149.0,
            valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            atr_period=3,
            atr_value=2.5,
        )
        assert s.symbol == "AAPL"
        assert s.side == "LONG"
        assert s.open_price == 150.0

    def test_valid_short_signal(self) -> None:
        s = TradingSignal(
            symbol="TSLA",
            side="SHORT",
            strategy_id="test-strat",
            open_price=200.0,
            entry_price=199.0,
            stop_loss=201.0,
            valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            atr_value=1.5,
        )
        assert s.side == "SHORT"

    def test_defaults(self) -> None:
        s = TradingSignal(
            symbol="AAPL",
            side="LONG",
            open_price=150.0,
            entry_price=151.0,
            stop_loss=149.0,
            valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            atr_value=2.5,
        )
        assert s.strategy_id == ""
        assert s.atr_period == 3
        # atr_value is required, no default

    def test_invalid_side(self) -> None:
        with pytest.raises(ValidationError):
            TradingSignal(
                symbol="AAPL",
                side="BUY",  # invalid
                open_price=150.0,
                entry_price=151.0,
                stop_loss=149.0,
                valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            )

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            TradingSignal(symbol="AAPL")  # type: ignore[arg-type]

    def test_serialization_roundtrip(self) -> None:
        s = TradingSignal(
            symbol="AAPL",
            side="LONG",
            strategy_id="test",
            open_price=150.0,
            entry_price=151.0,
            stop_loss=149.0,
            valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            atr_period=3,
            atr_value=2.5,
        )
        json_str = s.model_dump_json()
        s2 = TradingSignal.model_validate_json(json_str)
        assert s2.symbol == s.symbol
        assert s2.side == s.side
        assert s2.open_price == s.open_price
        assert s2.atr_value == s.atr_value
