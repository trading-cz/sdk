"""Unit tests for :mod:`tradingcz.sdk.market_data.clock`."""

# pylint: disable=protected-access

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest  # type: ignore

from tradingcz.sdk.market_data.clock import (
    TimeData,
    TimeKeeper,
    WarningEventTriggerCondition,
)


@pytest.fixture
def time_data() -> TimeData:
    """A stable trading-day snapshot used by the clock tests."""
    return TimeData(
        market_timestamp=datetime(2026, 8, 31, 14, 0, tzinfo=UTC),
        market_time_offset=timedelta(),
        last_market_open=datetime(2026, 8, 31, 13, 30, tzinfo=UTC),
        next_market_close=datetime(2026, 8, 31, 20, 0, tzinfo=UTC),
        next_market_open=datetime(2026, 9, 1, 13, 30, tzinfo=UTC),
        is_market_open=True,
        is_trading_day=True,
    )


@pytest.fixture
def keeper() -> TimeKeeper:
    return TimeKeeper(MagicMock())


@pytest.fixture
def mock_time_data() -> TimeData:
    now = datetime.now(tz=UTC)
    return TimeData(
        market_timestamp=now,
        market_time_offset=timedelta(seconds=0),
        next_market_close=now + timedelta(hours=1),
        next_market_open=now + timedelta(hours=12),
        last_market_open=now - timedelta(hours=5),
        is_market_open=True,
        is_trading_day=True,
    )


@pytest.fixture
def mock_provider(mock_time_data: TimeData) -> AsyncMock:
    provider = AsyncMock()
    provider.get_current_time_data.return_value = mock_time_data
    return provider


def test_uninitialized_access_raises_runtime_error(mock_provider: AsyncMock):
    """Guarantees uninitialized state protection works before sync."""
    tk = TimeKeeper(market_clock_provider=mock_provider)

    with pytest.raises(RuntimeError, match="uninitialized"):
        _ = tk.active_time_data
    with pytest.raises(RuntimeError, match="uninitialized"):
        _ = tk.market_time_utc


@pytest.mark.asyncio
async def test_start_timekeeping_populates_data(mock_provider: AsyncMock, mock_time_data: TimeData):
    """Verifies background loop fetches initial clock payload on start."""
    tk = TimeKeeper(market_clock_provider=mock_provider)

    await tk.start_timekeeping()
    assert tk.is_time_data_stale is True
    await asyncio.sleep(0.01)  # Yield to allow background loop 1st tick

    assert tk.active_time_data == mock_time_data
    assert tk.is_time_data_stale is False
    mock_provider.get_current_time_data.assert_called_once()

    await tk.stop_timekeeping()


@pytest.mark.asyncio
async def test_warning_event_fires_when_due(mock_provider: AsyncMock, mock_time_data: TimeData):
    """Verifies warning event fires when target threshold is reached."""
    now = datetime.now(tz=UTC)
    mock_time_data = mock_time_data.model_copy(update={"next_market_close": now + timedelta(minutes=10)})
    mock_provider.get_current_time_data.return_value = mock_time_data
    tk = TimeKeeper(market_clock_provider=mock_provider)

    event = tk.get_warning_event(WarningEventTriggerCondition.MINUTES_BEFORE_CLOSE, 15)
    assert not event.is_set()

    await tk.start_timekeeping()
    await asyncio.sleep(0.01)

    assert event.is_set()
    await tk.stop_timekeeping()


@pytest.mark.asyncio
async def test_run_loop_clears_fired_warnings_when_market_has_closed(mock_time_data: TimeData, mock_provider: AsyncMock) -> None:
    """Verifies that warning events are cleared when the market closes, even if they were previously fired."""
    now = datetime.now(tz=UTC)
    closed_session = mock_time_data.model_copy(
        update={
            "next_market_close": now - timedelta(seconds=1),
            "is_market_open": False,
        }
    )
    next_session = mock_time_data.model_copy(
        update={
            "next_market_close": now + timedelta(hours=24),
            "is_market_open": False,
        }
    )
    mock_provider.get_current_time_data.side_effect = [closed_session, next_session]

    tk = TimeKeeper(market_clock_provider=mock_provider)
    event = tk.get_warning_event(WarningEventTriggerCondition.MINUTES_BEFORE_CLOSE, 15)
    event.set()
    assert event.is_set()

    await tk.start_timekeeping()
    await asyncio.sleep(0.01)  # Yield to allow background ticks to process

    assert not event.is_set()
    assert mock_provider.get_current_time_data.call_count == 2

    await tk.stop_timekeeping()
