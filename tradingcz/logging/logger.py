"""Logging setup"""

import logging
import sys

_INTERNAL_PREFIXES = ["tradingcz", "__main__"]


# class DynamicAllowlistFilter(logging.Filter):
#     """Only pass log records whose name starts with an allowed prefix."""

#     def __init__(self, allowed_prefixes: list[str]) -> None:
#         super().__init__()
#         self.allowed_prefixes = tuple(allowed_prefixes)

#     def filter(self, record: logging.LogRecord) -> bool:
#         # startswith() handles sub-loggers (e.g., 'kafka.producer') automatically
#         return record.name.startswith(self.allowed_prefixes)


def setup_logging(app_level: str = "INFO", external_loggers: dict[str, str] | None = None) -> None:
    """
    Configure logging with a dynamic allowlist.


    Args:
        app_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        external_loggers: Optional dict of external logger names and their desired log level
                         (e.g.,: {"kafka": "WARNING", "alpaca": "DEBUG"}
    """
    format_string = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if external_loggers:
        for name, level_str in external_loggers.items():
            level = getattr(logging, level_str.upper(), logging.WARNING)
            logging.getLogger(name).setLevel(level)

    for prefix in _INTERNAL_PREFIXES:
        logging.getLogger(prefix).setLevel(getattr(logging, app_level.upper()))

    stdout_handler = logging.StreamHandler(sys.stdout)

    stdout_handler.setFormatter(format_string)

    root_logger.addHandler(stdout_handler)

    logging.captureWarnings(True)
    sys.excepthook = handle_exception

def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions."""
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
