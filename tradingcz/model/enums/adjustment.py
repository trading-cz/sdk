"""Adjustment enumeration for corporate actions."""

from enum import Enum


class Adjustment(str, Enum):
    """Corporate action adjustment for historical bars.
    
    Critical for accurate backtesting - unadjusted data causes false signals.
    
    Example:
        from tradingcz.model import Adjustment
        
        adj = Adjustment.ALL  # Recommended for backtesting
    """
    RAW = "raw"           # No adjustment
    SPLIT = "split"       # Adjusted for stock splits only
    DIVIDEND = "dividend" # Adjusted for dividends only
    ALL = "all"           # Adjusted for splits + dividends (recommended)
