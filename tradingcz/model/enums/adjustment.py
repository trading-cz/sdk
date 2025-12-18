"""Adjustment enumeration for corporate actions.
Corporate action adjustment for historical bars.
Critical for accurate backtesting - unadjusted data causes false signals.
"""

from enum import Enum


class Adjustment(str, Enum):
    RAW = "raw"           # No adjustment
    SPLIT = "split"       # Adjusted for stock splits only
    DIVIDEND = "dividend" # Adjusted for dividends only
    ALL = "all"           # Adjusted for splits + dividends (recommended)
