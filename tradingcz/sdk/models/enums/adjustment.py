from enum import StrEnum


class Adjustment(StrEnum):
    RAW = "raw"  # No adjustment
    SPLIT = "split"  # Adjusted for stock splits only
    DIVIDEND = "dividend"  # Adjusted for dividends only
    ALL = "all"  # Adjusted for splits + dividends (recommended)
