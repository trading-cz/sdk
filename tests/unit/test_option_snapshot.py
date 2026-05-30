"""Unit tests for OptionSnapshot model."""

from tradingcz.model.ingestion import OptionSnapshot, Quote, Trade


def test_option_snapshot_minimal() -> None:
    """OptionSnapshot can be created with just a symbol."""
    snap = OptionSnapshot(symbol="AAPL240621C00250000")
    assert snap.symbol == "AAPL240621C00250000"
    assert snap.latest_trade is None
    assert snap.implied_volatility is None
    assert snap.delta is None


def test_option_snapshot_full() -> None:
    """OptionSnapshot accepts trade, quote, greeks, and IV."""
    snap = OptionSnapshot(
        symbol="AAPL240621P00200000",
        latest_trade=Trade(
            symbol="AAPL240621P00200000",
            timestamp="2024-06-21T15:30:00Z",  # type: ignore[arg-type]
            price=5.25,
            size=10,
            exchange="CBOE",
        ),
        latest_quote=Quote(
            symbol="AAPL240621P00200000",
            timestamp="2024-06-21T15:30:00Z",  # type: ignore[arg-type]
            bid_price=5.20,
            ask_price=5.30,
        ),
        implied_volatility=0.35,
        delta=-0.45,
        gamma=0.03,
        theta=-0.02,
        vega=0.15,
        rho=-0.01,
    )
    assert snap.symbol == "AAPL240621P00200000"
    assert snap.latest_trade is not None
    assert snap.latest_trade.price == 5.25
    assert snap.implied_volatility == 0.35
    assert snap.delta == -0.45
    assert snap.gamma == 0.03


def test_option_snapshot_frozen() -> None:
    """OptionSnapshot is immutable (frozen model)."""
    snap = OptionSnapshot(symbol="SPY240621C00400000", implied_volatility=0.20)
    try:
        snap.implied_volatility = 0.30  # type: ignore[misc]
        raise AssertionError("Should not be able to mutate frozen model")
    except Exception:
        pass  # expected — frozen model rejects mutation
