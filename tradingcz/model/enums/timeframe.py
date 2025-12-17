"""Timeframe enumeration for historical data."""

from enum import Enum


class Timeframe(str, Enum):
    """Canonical timeframes for historical bars.
    
    Providers must map these to their native timeframe format.
    Only includes timeframes that most providers support.
    
    Example:
        from tradingcz.model import Timeframe
        
        tf = Timeframe.MINUTE_5
        print(tf.value)  # "5Min"
    """
    MINUTE_1 = "1Min"
    MINUTE_5 = "5Min"
    MINUTE_15 = "15Min"
    HOUR_1 = "1Hour"
    DAY = "1Day"
