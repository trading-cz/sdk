"""Unit tests for tradingcz.sdk.retry — generic async retry wrapper."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tradingcz.common.retry import Retry


class TransientError(RuntimeError):
    """Simulates a transient failure that recovers after N attempts."""


class TestRetry:
    """Four essential scenarios covering the Retry wrapper's behaviour."""

    @pytest.mark.asyncio
    async def test_succeeds(self) -> None:
        """Returns result on first attempt, or after retries if transient failures occur."""
        retry = Retry(max_retries=3, delay=0.01)

        # Immediate success — no retries
        assert await retry.call(lambda: asyncio.sleep(0, result="instant")) == "instant"

        # Success after 2 transient failures
        count = [0]

        async def flaky() -> str:
            count[0] += 1
            if count[0] < 3:
                raise TransientError(f"fail #{count[0]}")
            return "recovered"

        result = await retry.call(flaky)
        assert result == "recovered"
        assert retry.attempts == 2  # cumulative: 0 + 2 failures

    @pytest.mark.asyncio
    async def test_exhausts_retries(self) -> None:
        """Raises the last exception when all attempts fail."""
        retry = Retry(max_retries=2, delay=0.01)

        with pytest.raises(TransientError, match="always fails"):
            await retry.call(
                lambda: (_ for _ in ()).throw(TransientError("always fails"))
            )
        assert retry.attempts == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_passes_through(self) -> None:
        """BaseException (CancelledError, KeyboardInterrupt) propagates immediately, no retry."""
        retry = Retry(max_retries=5, delay=0.01)

        with pytest.raises(asyncio.CancelledError):
            await retry.call(lambda: (_ for _ in ()).throw(asyncio.CancelledError()))
        assert retry.attempts == 0  # never caught by the Exception handler

    @pytest.mark.asyncio
    async def test_waits_between_retries(self) -> None:
        """Sleeps for configured delay between retries; no sleep on immediate success."""
        retry = Retry(max_retries=2, delay=1.5)
        count = [0]

        async def flaky() -> str:
            count[0] += 1
            if count[0] < 2:
                raise TransientError("fail")
            return "ok"

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await retry.call(flaky)

        assert result == "ok"
        assert mock_sleep.call_count == 1  # one failure → one retry sleep
        mock_sleep.assert_called_with(1.5)
