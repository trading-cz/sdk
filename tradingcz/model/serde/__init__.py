"""Serialization helpers for domain models.

This package intentionally contains **transport-agnostic** serializers (JSON/CSV).
Provider-specific conversions belong in provider repos (e.g. ingestion-alpaca).
"""

from .csv import (
    bars_from_csv,
    bars_to_csv,
)
from .json import (
    bar_from_dict,
    bar_from_json,
    bar_to_dict,
    bar_to_json,
    quote_from_dict,
    quote_from_json,
    quote_to_dict,
    quote_to_json,
    snapshot_from_dict,
    snapshot_from_json,
    snapshot_to_dict,
    snapshot_to_json,
    trade_from_dict,
    trade_from_json,
    trade_to_dict,
    trade_to_json,
)

__all__ = [
    # JSON serialization
    "bar_to_dict",
    "bar_from_dict",
    "bar_to_json",
    "bar_from_json",
    "quote_to_dict",
    "quote_from_dict",
    "quote_to_json",
    "quote_from_json",
    "trade_to_dict",
    "trade_from_dict",
    "trade_to_json",
    "trade_from_json",
    "snapshot_to_dict",
    "snapshot_from_dict",
    "snapshot_to_json",
    "snapshot_from_json",
    # CSV serialization
    "bars_to_csv",
    "bars_from_csv",
]
