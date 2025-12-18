"""Basic test to verify trading-sdk imports work correctly."""

from tradingcz.model import Bar, Quote, Trade, Timeframe, Adjustment


def test_model_imports() -> None:
    """Test that core model classes can be imported."""
    assert Bar is not None
    assert Quote is not None
    assert Trade is not None


def test_enums_import() -> None:
    """Test that enums can be imported."""
    assert Timeframe is not None
    assert Adjustment is not None


def test_timeframe_enum_values() -> None:
    """Test Timeframe enum has expected values."""
    assert hasattr(Timeframe, "MINUTE_1")
    assert hasattr(Timeframe, "MINUTE_5")
    assert hasattr(Timeframe, "DAY")


def test_adjustment_enum_values() -> None:
    """Test Adjustment enum has expected values."""
    assert hasattr(Adjustment, "RAW")
    assert hasattr(Adjustment, "ALL")
