"""Logging setup utilities.

Consolidated from previous versions in logger.py and setup.py.
"""

import logging
import sys


def setup_logging(
    level: str = "INFO",
    external_loggers: dict[str, str] | None = None,
    format_string: str | None = None,
) -> None:
    """Configure logging for the application.

    Initializes root logging and optionally sets levels for external library
    loggers (e.g., ``{"kafka": "WARNING", "aiokafka": "WARNING"}``).

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        external_loggers: Optional dict mapping logger name → log level string.
        format_string: Custom format string. If None, uses default format.
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if external_loggers:
        for name, level_str in external_loggers.items():
            logging.getLogger(name).setLevel(getattr(logging, level_str.upper(), logging.WARNING))

    logging.captureWarnings(True)
