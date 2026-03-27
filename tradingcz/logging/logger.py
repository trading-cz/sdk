"""Global logging for the application."""

import logging
import sys
from typing import Any

_ALLOWED_PREFIXES = ("tradingcz", "__main__")


class AllowlistFilter(logging.Filter):
    """Only pass log records whose logger name starts with an allowed prefix."""

    def __init__(self, allowed_prefixes: list[str]) -> None:
        super().__init__()
        self.allowed_prefixes = tuple(allowed_prefixes)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(self.allowed_prefixes)


def setup_logging() -> None:  # env: str) -> None:
    """Configure application-wide logging.

    Writes INFO and below to stdout, WARNING and above to stderr.
    Restricts output to log records whose logger name starts
    with one of the provided prefixes.
    """

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    formatter: logging.Formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    allowlist = AllowlistFilter(_ALLOWED_PREFIXES)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)
    stdout_handler.addFilter(allowlist)
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.addFilter(allowlist)
    logger.addHandler(stderr_handler)

    logging.captureWarnings(True)
    logging.getLogger("py.warnings").addHandler(stderr_handler)

    sys.excepthook = handle_exception


def handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: Any,
) -> None:
    """Handle uncaught exceptions."""

    logging.error("Uncaught exception (be custom)", exc_info=(exc_type, exc_value, exc_traceback))
