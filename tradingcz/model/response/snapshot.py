"""HTTP response model for Snapshot (aggregated market state) data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tradingcz.model.domain.snapshot import Snapshot


class SnapshotResponse(BaseModel):
    """HTTP response model for a market snapshot."""
    latest_trade: dict | None = None
    latest_quote: dict | None = None
    minute_bar: dict | None = None
    daily_bar: dict | None = None
    previous_daily_bar: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "latest_trade": {
                    "timestamp": "2024-01-15T14:30:00+00:00",
                    "price": 150.50,
                    "size": 1000,
                    "exchange": "XNAS"
                },
                "latest_quote": {
                    "timestamp": "2024-01-15T14:30:00+00:00",
                    "bid_price": 150.49,
                    "ask_price": 150.51,
                    "bid_size": 500,
                    "ask_size": 600
                },
                "minute_bar": {
                    "timestamp": "2024-01-15T14:30:00+00:00",
                    "open": 150.45,
                    "high": 150.60,
                    "low": 150.40,
                    "close": 150.50,
                    "volume": 50000
                },
                "daily_bar": {
                    "timestamp": "2024-01-15T00:00:00+00:00",
                    "open": 149.50,
                    "high": 151.00,
                    "low": 149.40,
                    "close": 150.50,
                    "volume": 5000000
                }
            }
        }
    )


def snapshot_to_response(snapshot: Snapshot) -> SnapshotResponse:
    """Convert Snapshot domain model to HTTP response.

    Args:
        snapshot: Snapshot domain model

    Returns:
        SnapshotResponse (Pydantic model) ready for JSON serialization
    """
    from tradingcz.model.serde.json import (
        bar_to_dict,
        quote_to_dict,
        trade_to_dict,
    )

    return SnapshotResponse(
        latest_trade=trade_to_dict(snapshot.latest_trade) if snapshot.latest_trade else None,
        latest_quote=quote_to_dict(snapshot.latest_quote) if snapshot.latest_quote else None,
        minute_bar=bar_to_dict(snapshot.minute_bar) if snapshot.minute_bar else None,
        daily_bar=bar_to_dict(snapshot.daily_bar) if snapshot.daily_bar else None,
        previous_daily_bar=bar_to_dict(snapshot.previous_daily_bar) if snapshot.previous_daily_bar else None,
    )
