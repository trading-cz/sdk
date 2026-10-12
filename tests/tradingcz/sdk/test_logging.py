"""Unit tests for setup_logging."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from tradingcz.sdk.logging import setup_logging


@pytest.fixture
def root_handlers() -> Iterator[None]:
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for handler in [h for h in root.handlers if h not in before]:
        root.removeHandler(handler)
        handler.close()


@pytest.mark.usefixtures("root_handlers")
def test_setup_logging_twice_keeps_one_handler_per_target(tmp_path: Path) -> None:
    log_file = str(tmp_path / "app.log")
    setup_logging(log_file=log_file)
    setup_logging(log_file=log_file)
    ours = [h for h in logging.getLogger().handlers if h.get_name() == "tradingcz"]
    assert len(ours) == 2  # stdout + file
