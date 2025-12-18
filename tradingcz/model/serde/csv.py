"""CSV serialization for domain models.

CSV is primarily for exports/artifacts/backtesting pipelines.
We keep this in the SDK because it is provider-agnostic.
"""

from __future__ import annotations

import csv
import io
from dataclasses import fields
from datetime import datetime

from tradingcz.model.domain.bar import Bar

# Dynamically derive field names from Bar dataclass to stay in sync with model changes
_BAR_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Bar))


def bars_to_csv(bars: list[Bar]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_BAR_FIELDS)
    writer.writeheader()

    for bar in bars:  # pylint: disable=C0104
        writer.writerow(
            {
                "symbol": bar.symbol,
                "timestamp": bar.timestamp.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "trade_count": "" if bar.trade_count is None else bar.trade_count,
                "vwap": "" if bar.vwap is None else bar.vwap,
            }
        )

    return buf.getvalue()


def bars_from_csv(payload: str) -> list[Bar]:
    buf = io.StringIO(payload)
    reader = csv.DictReader(buf)

    out: list[Bar] = []
    for row in reader:
        out.append(
            Bar(
                symbol=row["symbol"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                trade_count=(int(row["trade_count"]) if row.get("trade_count") else None),
                vwap=(float(row["vwap"]) if row.get("vwap") else None),
            )
        )

    return out
