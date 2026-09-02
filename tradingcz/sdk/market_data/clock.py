"""TimeKeeper — market clock wrapper that fires asyncio events before close.

A client that wraps a ``MarketClockProvider`` and periodically fires
``asyncio.Event`` objects when the market approaches close.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum, auto
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType, ServiceRequestType
from tradingcz.sdk.models.events.service_request_event import ServiceRequestEvent
from tradingcz.sdk.registry import register_event


class TimeData(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_timestamp: datetime = Field(..., description="Market time at the moment of last sync")
    market_time_offset: timedelta = Field(..., description="Market time offset to local time at executor (api contact)")
    next_market_close: datetime = Field(..., description="Next market close time")
    next_market_open: datetime = Field(..., description="Next market open time")
    last_market_open: datetime = Field(..., description="Last market open time")
    is_market_open: bool = Field(..., description="Is the market open?")
    is_trading_day: bool = Field(..., description="It is trading day today?")


@register_event(EventType.TIME_DATA_RESPONSE)
class TimeDataResponse(BaseModel):
    """Response to a balance query."""

    event_id: UUID = Field(..., description="Unique identifier for this event")
    time_data: TimeData = Field(..., description="Time data model")


class MarketClockProvider(Protocol):
    """Contract for a market clock provider."""

    async def get_current_time_data(self) -> TimeData: ...


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

    async def get_current_time_data(self) -> TimeData:
        """Get the current time data via transport layer."""
        req: ServiceRequestEvent = ServiceRequestEvent(service=ServiceRequestType.REQUEST_TIME_DATA)
        resp: TimeDataResponse = await self._rr.request(req=req, response_type=TimeDataResponse)
        return resp.time_data


class WarningEventTriggerCondition(StrEnum):
    MINUTES_BEFORE_CLOSE = "MINUTES_BEFORE_CLOSE"
    MINUTES_AFTER_OPEN = "MINUTES_AFTER_OPEN"


class TimeDataStaleReason(Enum):
    NOT_STALE = auto()
    NOT_INITIALIZED = auto()
    INTERVAL_EXPIRED = auto()
    MARKET_OPENED = auto()
    MARKET_CLOSED = auto()


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
        self._last_sync_monotonic: float | None = None
        self._task: asyncio.Task | None = None
        self._time_data: TimeData | None = None

    @property
    def market_time_utc(self) -> datetime:
        """Returns real market time, computed from local time + offset. Raises if clock is not initialized"""
        return datetime.now(tz=UTC) + self.active_time_data.market_time_offset

    @property
    def active_time_data(self) -> TimeData:
        """Centralized invariant guard. Guaranteed non-None for internal callers. Raises if clock is not initialized"""
        if self._time_data is None:
            raise RuntimeError("TimeKeeper data is uninitialized. Call start_timekeeping() first.")
        return self._time_data

    @property
    def is_time_data_stale(self) -> bool:
        """Public check indicating whether cached time data needs a refresh."""
        return self._get_stale_reason(self._last_sync_monotonic) != TimeDataStaleReason.NOT_STALE

    @property
    def seconds_until_market_close(self) -> int:
        """Calculate the number of seconds until the market closes."""
        time_to_close = self.active_time_data.next_market_close - self.market_time_utc
        return int(time_to_close.total_seconds())

    async def start_timekeeping(self) -> None:
        """Start the time keeper heartbeat."""
        self._task = asyncio.create_task(self._run_loop(), name="time-keeper-heartbeat")
        self._task.add_done_callback(self._handle_task_result)

    def _handle_task_result(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass  # Expected when calling task.cancel()
        except Exception as exc:
            logger.critical("TimeKeeper heartbeat loop crashed unexpectedly", exc_info=exc)

    async def stop_timekeeping(self) -> None:
        """Stop the time keeper heartbeat."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def force_sync(self) -> None:
        self._reschedule_signal.set()

    def get_warning_event(self, condition: WarningEventTriggerCondition, offset_minutes: int) -> asyncio.Event:
        """Get or create an event that will be set when offset time from some trigger condition is reached.

        condition: WarningEventTriggerCondition — the condition to trigger the event (e.g., before market close, after market open)
        offset_minutes: int — the number of minutes before or after the condition to trigger the event.
        """
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

    def _get_stale_reason(self, last_sync_monotonic: float | None) -> TimeDataStaleReason:
        """Check more complex reasons why data could be stale - market close/open event corossed, etc."""
        if self._time_data is None or last_sync_monotonic is None:
            return TimeDataStaleReason.NOT_INITIALIZED
        if time.monotonic() - last_sync_monotonic >= self._sync_interval:
            return TimeDataStaleReason.INTERVAL_EXPIRED
        now = self.market_time_utc
        if now >= self.active_time_data.next_market_close:
            return TimeDataStaleReason.MARKET_CLOSED
        if now >= self.active_time_data.next_market_open:
            return TimeDataStaleReason.MARKET_OPENED

        return TimeDataStaleReason.NOT_STALE

    def _get_next_warn_event_time(self) -> datetime | None:
        """Find out when the next warning event is to be set, and return seconds remaining to that."""
        upcomming_trigger_times: list[datetime] = []
        now = self.market_time_utc
        for (cond, minutes), event in self._market_warning_events.items():
            if event.is_set():
                continue
            target_time = self._compute_datetime_for_warning_event(cond, minutes)
            if target_time > now:
                upcomming_trigger_times.append(target_time)
        return min(upcomming_trigger_times) if upcomming_trigger_times else None

    def _compute_datetime_for_warning_event(self, cond: WarningEventTriggerCondition, minutes: int) -> datetime:
        """Calculate the exact target datetime for a warning event condition."""
        match cond:
            case WarningEventTriggerCondition.MINUTES_BEFORE_CLOSE:
                return self.active_time_data.next_market_close - timedelta(minutes=minutes)
            case WarningEventTriggerCondition.MINUTES_AFTER_OPEN:
                today_target = self.active_time_data.last_market_open + timedelta(minutes=minutes)
                if today_target > self.market_time_utc:
                    return today_target
                return self.active_time_data.next_market_open + timedelta(minutes=minutes)

            case _:
                raise ValueError(f"Unsupported trigger condition: {cond}")

    def _clear_warning_events(self) -> None:
        """All registered warning events will be cleared."""
        for event in self._market_warning_events.values():
            if event.is_set():
                event.clear()

    def _trigger_due_events(self) -> None:
        """Trigger any registered events whose target time has arrived or passed."""
        now = self.market_time_utc
        for (cond, minutes), event in self._market_warning_events.items():
            if event.is_set():
                continue
            target_time = self._compute_datetime_for_warning_event(cond, minutes)
            if now >= target_time:
                event.set()
                logger.debug("Fired warning event for %s offset by %d minutes.", cond, minutes)

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep for 'seconds' UNLESS _reschedule_signal is set first"""
        try:
            await asyncio.wait_for(self._reschedule_signal.wait(), timeout=seconds)
            self._reschedule_signal.clear()
        except TimeoutError:
            pass  # Slept full duration naturally

    async def _run_loop(self) -> None:
        """Main time keeper loop — refreshes clock cache and fires warning events."""

        while True:
            stale_reason = self._get_stale_reason(self._last_sync_monotonic)
            logger.debug("Time keeper loop tick, stale reason: %s", stale_reason)
            if stale_reason != TimeDataStaleReason.NOT_STALE:
                # On market close (end of trading day), clear all warning events that were set.
                if stale_reason == TimeDataStaleReason.MARKET_CLOSED:
                    self._clear_warning_events()
                logger.debug("Getting current time data")
                self._time_data = await self._market_clock_provider.get_current_time_data()
                logger.debug("current time data: %s", self._time_data)
                self._last_sync_monotonic = time.monotonic()
                logger.info(
                    "Refreshing market clock cache from Broker API. New data:\n Market time: %s,\n Next open: %s,\n Next close: %s",
                    self.market_time_utc,
                    self.active_time_data.next_market_open,
                    self.active_time_data.next_market_close,
                )

            self._trigger_due_events()
            now = self.market_time_utc

            # How many seconds left to the next time this loop should fire (if no new warning events are registered)
            next_warning_at = self._get_next_warn_event_time()
            next_event = (next_warning_at - now).total_seconds() if next_warning_at is not None else float("inf")
            time_to_next_open = self.active_time_data.next_market_open - now
            time_to_next_close = self.active_time_data.next_market_close - now

            sleep_seconds = min(next_event, float(self._sync_interval), time_to_next_open.total_seconds(), time_to_next_close.total_seconds())

            if sleep_seconds > 0:
                await self._interruptible_sleep(sleep_seconds)
