"""Logging setup utilities."""

import logging
import sys


def setup_logging(
    level: str = "INFO",
    external_loggers: list[str] | None = None,
    format_string: str | None = None,
) -> None:
    """Configure logging for the application.

    Initializes root logging and optionally configures external library loggers
    with consistent formatting without coupling to specific implementations.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        external_loggers: Optional list of external logger names to format
                         (e.g., ["uvicorn.access", "uvicorn.error", "uvicorn"])
        format_string: Custom format string. If None, uses default format.
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure root logging
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Configure external loggers if provided
    if external_loggers:
        formatter = logging.Formatter(format_string)
        log_level = getattr(logging, level.upper())
        for logger_name in external_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(log_level)
            for handler in logger.handlers:
                handler.setFormatter(formatter)
