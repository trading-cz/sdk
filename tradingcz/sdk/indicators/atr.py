"""Average True Range (ATR) indicator — Wilder's method."""

from tradingcz.sdk.models.market import Bar


def calculate_atr(bars: list[Bar], period: int) -> float:
    """Calculate Average True Range (Wilder) over the last *period* bars.

    TR = max(High - Low, |High - PrevClose|, |Low - PrevClose|)

    Args:
        bars: List of Bar objects sorted ascending by timestamp.
        period: Number of periods for ATR.

    Returns:
        Simple moving average of the last *period* true ranges.

    Raises:
        ValueError: If fewer than ``period + 1`` bars are provided.
    """
    if len(bars) < period + 1:
        raise ValueError(
            f"Need at least {period + 1} bars for ATR({period}), got {len(bars)}"
        )

    true_ranges: list[float] = []
    for i in range(1, len(bars)):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i - 1].close
        true_ranges.append(
            max(high - low, abs(high - prev_close), abs(low - prev_close))
        )

    return sum(true_ranges[-period:]) / period
