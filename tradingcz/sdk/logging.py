"""Logging setup and configuration for trading-cz SDK."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any


class _UTCFormatter(logging.Formatter):
    """Formatter that uses UTC timestamps without mutating global state."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=UTC)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(sep=" ", timespec="milliseconds")


class LokiJSONFormatter(logging.Formatter):
    """Formats logs for Loki with standardized keys for LogQL."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


_DEFAULT_APP_PREFIXES: tuple[str, ...] = ("tradingcz", "__main__")


def setup_logging(
    app_level: str = "INFO",
    external_loggers: dict[str, str] | None = None,
    log_file: str | None = None,
    *,
    app_prefixes: Sequence[str] = _DEFAULT_APP_PREFIXES,
    capture_uncaught: bool = False,
) -> None:
    """Configure logging for the application.

    Args:
        app_level: Logging level for application loggers (DEBUG, INFO, …).
        external_loggers: ``{name: level}`` for third-party loggers
            (e.g. ``{"kafka": "WARNING", "alpaca": "DEBUG"}``).
        log_file: When set, also write DEBUG-level logs to this file
            (convenience for local development).
        app_prefixes: Logger name prefixes treated as application loggers.
            Defaults to ``("tradingcz", "__main__")``.
        capture_uncaught: When ``True``, install ``sys.excepthook`` so
            unhandled exceptions are logged before the process exits.
            Off by default — enable only when you cannot wrap ``main()``
            in a try/except.
    """
    formatter = _UTCFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if external_loggers:
        for name, level_str in external_loggers.items():
            level = getattr(logging, level_str.upper(), logging.WARNING)
            logging.getLogger(name).setLevel(level)

    app_level_value = getattr(logging, app_level.upper(), logging.INFO)
    for prefix in app_prefixes:
        logging.getLogger(prefix).setLevel(app_level_value)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    logging.captureWarnings(True)

    if capture_uncaught:
        sys.excepthook = _handle_exception

    # ── Optional file logging (local dev) ────────────────────────────
    if log_file is not None:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        logging.getLogger("py.warnings").addHandler(file_handler)


def _handle_exception(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any
) -> None:
    """Log uncaught exceptions before the interpreter exits."""
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


__all__ = ["LokiJSONFormatter", "setup_logging"]


__all__ = ["LokiJSONFormatter", "setup_logging"]
