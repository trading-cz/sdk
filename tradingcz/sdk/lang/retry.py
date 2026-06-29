"""Async retry wrapper — call any async operation with retries on failure."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class Retry:
    """Call an async operation with retries on transient failure."""

    def __init__(self, max_retries: int = 3, delay: float = 2.0) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if delay < 0:
            raise ValueError("delay must be >= 0")
        self.max_retries = max_retries
        self.delay = delay
        self._attempts = 0

    async def call[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        """Execute *operation*, retrying on any ``Exception``.

        ``BaseException`` subclasses (CancelledError, KeyboardInterrupt)
        propagate immediately.
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await operation()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                last_exc = exc
                self._attempts += 1
                if attempt < self.max_retries:
                    logger.warning( "Retry %d/%d: %s — retrying in %.1fs", attempt + 1, self.max_retries + 1, exc, self.delay, )
                    await asyncio.sleep(self.delay)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Retry.call: no exception captured")

    @property
    def attempts(self) -> int:
        """Total retry attempts made across all ``call()`` invocations."""
        return self._attempts

