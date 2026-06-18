"""TimeKeeper — market clock wrapper that fires asyncio events before close.

A client that wraps a ``MarketClockProvider`` and periodically fires
``asyncio.Event`` objects when the market approaches close.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Protocol


class MarketClockProvider(Protocol):
    """Contract for a market clock provider."""

    async def get_current_market_time(self) -> datetime: ...

    async def get_next_market_close(self) -> datetime: ...

    async def get_next_market_open(self) -> datetime: ...

    async def is_market_open(self) -> bool: ...

    async def refresh_clock(self) -> None: ...


logger = logging.getLogger(__name__)


class TimeKeeper:
    """Track market time and fire warning events before market close."""

    def __init__(
        self,
        market_clock_provider: MarketClockProvider,
        sync_interval_seconds: int = 3600,
    ) -> None:

        self._clock: MarketClockProvider = market_clock_provider
        self._sync_interval: int = sync_interval_seconds
        self._market_close_warning_events: dict[int, asyncio.Event] = {}
        self._task: asyncio.Task | None = None

    async def start_timekeeping(self) -> None:
        """Begin the heartbeat."""
        self._task = asyncio.create_task(self.run_loop(), name="time-keeper-heartbeat")

    async def stop_timekeeping(self) -> None:
        """Stop the heartbeat."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def get_warning_event(self, minutes_before_close: int) -> asyncio.Event:
        """Get or create an event that will be set when the market is within the specified minutes of closing."""
        if minutes_before_close not in self._market_close_warning_events:
            self._market_close_warning_events[minutes_before_close] = asyncio.Event()
            logger.debug(
                "New warning event for market close in %d minutes created",
                minutes_before_close,
            )
        return self._market_close_warning_events[minutes_before_close]

    async def second_until_market_close(self) -> int:
        """Calculate the number of seconds until the market closes."""
        now = await self._clock.get_current_market_time()
        next_close = await self._clock.get_next_market_close()
        time_to_close = next_close - now
        return int(time_to_close.total_seconds())

    async def run_loop(self) -> None:
        """Main loop — refreshes clock cache and fires warning events."""
        last_sync_time: float | None = None
        minutes_remaining: int = 0
        while True:
            if (
                last_sync_time is None
                or time.monotonic() - last_sync_time >= self._sync_interval
            ):
                logger.info(
                    "Refreshing market clock cache from broker API source of truth..."
                )
                await self._clock.refresh_clock()
                logger.info(
                    "Refreshing market clock cache."
                    "New data:\n Market time: %s,\n Next open: %s,\n Next close: %s",
                    await self._clock.get_current_market_time(),
                    await self._clock.get_next_market_open(),
                    await self._clock.get_next_market_close(),
                )
                last_sync_time = time.monotonic()
            now: datetime = await self._clock.get_current_market_time()
            next_close: datetime = await self._clock.get_next_market_close()

            time_to_close: timedelta = next_close - now
            minutes_remaining_new = int(time_to_close.total_seconds() // 60)

            if minutes_remaining_new != minutes_remaining:
                minutes_remaining = minutes_remaining_new

            if minutes_remaining in self._market_close_warning_events:
                logger.debug(
                    "Firing warning event for market close in %d minutes for all waiting tasks...",
                    minutes_remaining,
                )
                event = self._market_close_warning_events[minutes_remaining]
                if not event.is_set():
                    event.set()

            await asyncio.sleep(1)


__all__ = ["TimeKeeper", "MarketClockProvider"]
