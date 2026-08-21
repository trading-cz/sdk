"""TimeKeeper — market clock wrapper that fires asyncio events before close.

A client that wraps a ``MarketClockProvider`` and periodically fires
``asyncio.Event`` objects when the market approaches close.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType, ServiceRequestType
from tradingcz.sdk.models.events.service_request_event import ServiceRequestEvent
from tradingcz.sdk.registry import register_event


class TimeData(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_time_offset: timedelta = Field(..., description="Market time offset")
    next_market_close: datetime = Field(..., description="Next market close time")
    next_market_open: datetime = Field(..., description="Next market close time")
    last_market_open: datetime = Field(..., description="Last market open time")
    is_market_open: bool = Field(..., description="Is the market open?")
    is_trading_day: bool = Field(..., description="It is trading day today?")


@register_event(EventType.TIME_DATA_RESPONSE)
class TimeDataResponse(BaseModel):
    """Response to a balance query."""

    event_id: str
    time_data: TimeData


class WarningEventTriggerCondition(StrEnum):
    MINUTES_BEFORE_CLOSE = "MINUTES_BEFORE_CLOSE"
    MINUTES_AFTER_OPEN = "MINUTES_AFTER_OPEN"


class MarketClockProvider(Protocol):
    """Contract for a market clock provider."""

    async def get_current_time_data(self) -> TimeDataResponse: ...


logger = logging.getLogger(__name__)


class TransportMarketClockProvider(MarketClockProvider):
    """SDK implementation of market clock provider for apps other than executor. Using SDK transport layer to get data from executor."""

    def __init__(
        self,
        *,
        rr: RequestReply,
        default_timeout: float = 30.0,
    ) -> None:
        self._rr = rr
        self._default_timeout = default_timeout

    async def get_current_time_data(self) -> TimeDataResponse:
        """Get the current time data via transport layer."""
        req: ServiceRequestEvent = ServiceRequestEvent(service=ServiceRequestType.REQUEST_TIME_DATA)
        resp: TimeDataResponse = await self._rr.request(req=req, response_type=TimeDataResponse)
        return resp


class TimeKeeper:
    """Track market time and fire warning events before market close."""

    def __init__(
        self,
        market_clock_provider: MarketClockProvider,
        sync_interval_seconds: int = 3600,
    ) -> None:

        self._market_clock_provider: MarketClockProvider = market_clock_provider
        self._sync_interval: int = sync_interval_seconds
        self._market_warning_events: dict[tuple[WarningEventTriggerCondition, int], asyncio.Event] = {}
        self._reschedule_signal = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._time_data: TimeData | None = None

    @property
    def market_time(self) -> datetime:
        """Returns real market time, computed from local time + offset. Raises if clock is not initialized"""
        return datetime.now(tz=UTC) + self._active_time_data.market_time_offset

    @property
    def _active_time_data(self) -> TimeData:
        """Centralized invariant guard. Guaranteed non-None for internal callers. Raises if clock is not initialized"""
        if self._time_data is None:
            raise RuntimeError("TimeKeeper data is uninitialized. Call start_timekeeping() first.")
        return self._time_data

    @property
    def seconds_until_market_close(self) -> int:
        """Calculate the number of seconds until the market closes."""
        time_to_close = self._active_time_data.next_market_close - self.market_time
        return int(time_to_close.total_seconds())

    async def start_timekeeping(self) -> None:
        """Start the time keeper heartbeat."""
        self._task = asyncio.create_task(self._run_loop(), name="time-keeper-heartbeat")

    async def stop_timekeeping(self) -> None:
        """Stop the time keeper heartbeat."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def get_warning_event(self, condition: WarningEventTriggerCondition, offset_minutes: int) -> asyncio.Event:
        """Get or create an event that will be set when offset time from some trigger condition is reached.

        condition: WarningEventTriggerCondition — the condition to trigger the event (e.g., before market close, after market open)
        offset_minutes: int — the number of minutes before or after the condition to trigger the event"""

        key = (condition, offset_minutes)
        if key not in self._market_warning_events:
            self._market_warning_events[key] = asyncio.Event()
            logger.debug(
                "New warning event for %s in %d minutes created",
                condition,
                offset_minutes,
            )
            self._reschedule_signal.set()
        return self._market_warning_events[key]

    def _is_time_data_stale(self, last_sync_monotonic: float) -> bool:
        """Check more complex reasons why data could be stale - market close/open event corossed, etc."""

        stale_reasons = (
            # 1. sync_interval has passed
            (time.monotonic() - last_sync_monotonic >= self._sync_interval),
            # 2. Boundary crossing: We passed the cached next_market_close/next_market_open
            (self.market_time >= self._active_time_data.next_market_close or self.market_time >= self._active_time_data.next_market_open),
        )

        return any(stale_reasons)

    async def _interruptible_sleep(self, seconds: float) -> None:
        try:
            # Sleep for 'seconds' UNLESS _reschedule_signal is set first
            await asyncio.wait_for(self._reschedule_signal.wait(), timeout=seconds)
            self._reschedule_signal.clear()  # Woken up early by new event registration
        except TimeoutError:
            pass  # Slept full duration naturally

    def _calculate_earliest_target_time(self) -> datetime | None:
        """Find out when the next warning event is to be set, and return seconds remaining to that."""
        upcomming_trigger_times: list[datetime] = []
        for (cond, minutes), event in self._market_warning_events.items():
            if event.is_set():
                continue
            match cond:
                case WarningEventTriggerCondition.MINUTES_BEFORE_CLOSE:
                    upcomming_trigger_times.append(self._active_time_data.next_market_close - timedelta(minutes=minutes))

                case WarningEventTriggerCondition.MINUTES_AFTER_OPEN:
                    upcomming_trigger_times.append(self._active_time_data.last_market_open + timedelta(minutes=minutes))
                case _:
                    raise ValueError(f"Unsupported trigger condition: {cond}")
        return min(upcomming_trigger_times) if upcomming_trigger_times else None

    async def _run_loop(self) -> None:
        """Main time keeper loop — refreshes clock cache and fires warning events."""
        last_sync_monotonic: float | None = None
        while True:
            if self._time_data is None or last_sync_monotonic is None or self._is_time_data_stale(last_sync_monotonic):
                time_data_response: TimeDataResponse = await self._market_clock_provider.get_current_time_data()
                self._time_data = time_data_response.time_data
                last_sync_monotonic = time.monotonic()
                logger.info(
                    "Refreshing market clock cache from Broker API. New data:\n Market time: %s (offset: %s),\n Last open: %s,\n Next close: %s",
                    self.market_time,
                    self._time_data.market_time_offset,
                    self._time_data.last_market_open,
                    self._time_data.next_market_close,
                )

                next_target = self._calculate_earliest_target_time()
                time_to_next_open = self._time_data.next_market_open - self.market_time
                time_to_next_close = self._time_data.next_market_close - self.market_time

                if next_target is None:
                    sleep_seconds = min(float(self._sync_interval), time_to_next_open, time_to_next_close)
                else:
                    sleep_seconds = (next_target - self.market_time).total_seconds()

                # 3. Sleep efficiently until the next milestone or wakeup signal
                if sleep_seconds > 0:
                    await self._interruptible_sleep(sleep_seconds)

                # 4. Fire any events whose trigger time has arrived
                self._trigger_due_events()
