"""Logging setup and configuration for trading-cz SDK."""

import json
import logging
import sys
import time
from typing import Any


class LokiJSONFormatter(logging.Formatter):
    """Formats logs for Loki with standardized keys for LogQL."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
        }
        if record.exc_info:
            # Aggregating error types over time.
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


_INTERNAL_PREFIXES = ["tradingcz", "__main__"]


def setup_logging(
    app_level: str = "INFO",
    external_loggers: dict[str, str] | None = None,
    log_to_file: bool = False,
) -> None:
    """
    Configure logging with a dynamic allowlist.

    Args:
        app_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        external_loggers: Optional dict of external logger names and their desired log level
                         (e.g.,: {"kafka": "WARNING", "alpaca": "DEBUG"}
    """

    logging.Formatter.converter = time.gmtime
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if external_loggers:
        for name, level_str in external_loggers.items():
            level = getattr(logging, level_str.upper(), logging.WARNING)
            logging.getLogger(name).setLevel(level)

    for prefix in _INTERNAL_PREFIXES:
        logging.getLogger(prefix).setLevel(getattr(logging, app_level.upper()))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    logging.captureWarnings(True)
    sys.excepthook = handle_exception

    ############## LOCAL FILE LOGGING FOR DEVELOPMENT ##############

    if log_to_file:
        file_handler = logging.FileHandler("local_dev.log", mode="a")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        logging.getLogger("py.warnings").addHandler(file_handler)
    ############## LOCAL FILE LOGGING FOR DEVELOPMENT ##############


def handle_exception(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any
) -> None:
    """Handle uncaught exceptions."""
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


__all__ = ["LokiJSONFormatter", "setup_logging"]
