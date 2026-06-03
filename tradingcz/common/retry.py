"""Generic retry wrapper — call any async operation with retries on failure.

Simple two-parameter design::

    from tradingcz.common.retry import Retry

    retry = Retry(max_retries=3, delay=2.0)
    bars = await retry.call(lambda: client.bars(["AAPL"]))
    positions = await retry.call(lambda: client.get_positions())

Works with any async callable — data, positions, balance, orders, signals.
No coupling to Kafka, transport, or any specific client.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class Retry:
    """Call any async operation with retries on transient failure.

    Args:
        max_retries: Maximum retry attempts (total calls = max_retries + 1).
        delay: Seconds to wait between retries.

    Example::

        retry = Retry(max_retries=5, delay=2.0)
        result = await retry.call(lambda: app.stock.bars(["AAPL"]))
    """

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

        Only ``Exception`` subclasses trigger a retry — ``BaseException``
        subclasses (``KeyboardInterrupt``, ``SystemExit``, ``asyncio.CancelledError``)
        propagate immediately without retrying.

        Args:
            operation: An async callable (e.g. ``lambda: client.do_work()``).

        Returns:
            The return value of *operation* on success.

        Raises:
            The last exception raised by *operation* if all attempts are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await operation()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                last_exc = exc
                self._attempts += 1
                if attempt < self.max_retries:
                    logger.warning(
                        "Retry %d/%d: %s — retrying in %.1fs",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                        self.delay,
                    )
                    await asyncio.sleep(self.delay)

        raise last_exc  # type: ignore[misc]

    @property
    def attempts(self) -> int:
        """Total retry attempts made across all ``call()`` invocations."""
        return self._attempts
