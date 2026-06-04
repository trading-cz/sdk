"""Canonical timeframe format — the contract between strategies and ingestion.

Every strategy MUST use this enum (or its string values). Every broker
adapter MUST declare which subset it supports via :attr:`supported_timeframes`.

Format: ``"{amount}{unit}"`` — e.g. ``"4h"``, ``"15min"``, ``"1d"``.
No other format is accepted on the wire — Pydantic validation rejects
variants like ``"4Hour"`` or ``"4 Hours"`` at deserialization time.
"""

from enum import StrEnum


class Timeframe(StrEnum):
    """Canonical timeframe identifiers for the trading platform.

    String values are the wire format used in ``DataRequest.timeframe``.
    """

    # Minutes
    M1 = "1min"
    M2 = "2min"
    M3 = "3min"
    M5 = "5min"
    M10 = "10min"
    M15 = "15min"
    M30 = "30min"
    M45 = "45min"

    # Hours
    H1 = "1h"
    H2 = "2h"
    H3 = "3h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"

    # Daily
    D1 = "1d"

    # Weekly
    W1 = "1week"

    # Monthly
    MN1 = "1month"
