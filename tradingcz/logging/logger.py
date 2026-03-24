"""Global logging for the application."""

import logging
import os
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter


def setup_logging() -> None:  # env: str) -> None:
    """setup logging and return logger.
    There is a possibility to log in json format, or"""

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    app_env = os.getenv("APP_ENV")
    formatter: logging.Formatter | JsonFormatter
    if app_env == "local":
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        file_handler = logging.FileHandler("local_dev.log", mode="a")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logging.getLogger("py.warnings").addHandler(file_handler)
    else:
        formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        if app_env != "production":
            print(
                f"WARNING: APP_ENV='{app_env}' is not recognised. "
                "Defaulting to production (JSON) logging.",
                file=sys.stderr,
            )

    # TODO ALSO:
    # currently there is no way to adjust log levels without redeploying. Should
    # consider reading the level from an env var, which wouldm introduce capability to temporarily switch log levels:

    # pythonlog_level = os.getenv("LOG_LEVEL", "INFO").upper()
    # logger.setLevel(getattr(logging, log_level, logging.INFO))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)

    logging.captureWarnings(True)
    logging.getLogger("py.warnings").addHandler(stderr_handler)

    # Suppress SQLAlchemy's internal exception logging - these are handled at application level
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)

    sys.excepthook = handle_exception


def handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: Any,
) -> None:
    """Handle uncaught exceptions."""

    logging.error("Uncaught exception (be custom)", exc_info=(exc_type, exc_value, exc_traceback))
