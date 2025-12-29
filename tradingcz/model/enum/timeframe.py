from enum import Enum


class Timeframe(str, Enum):
    MINUTE_1 = "1Min"
    MINUTE_5 = "5Min"
    MINUTE_15 = "15Min"
    MINUTE_30 = "30Min"
    HOUR_1 = "1Hour"
    HOUR_4 = "4Hour"
    HOUR_8 = "8Hour"
    DAY = "1Day"
