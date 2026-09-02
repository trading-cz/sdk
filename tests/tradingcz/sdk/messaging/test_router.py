"""Unit tests for EventRouter — dispatch, filter, auto_commit, on_error."""
# pylint: disable=protected-access

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tradingcz.sdk.messaging.router import EventRouter
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType, ServiceRequestType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.models.events.service_request_event import ServiceRequestEvent
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

# ── Helpers ──────────────────────────────────────────────────────────────


def _settings() -> KafkaSettings:
    return KafkaSettings(bootstrap_servers="localhost:9092", consumer_group="test-router")


def _raw_msg(topic: str = "events", offset: int = 0) -> KafkaMessage:
    return KafkaMessage(payload=b"{}", topic=topic, offset=offset)


def _lifecycle(event: LifecycleEventType) -> LifecycleEvent:
    return LifecycleEvent(service_id="test-svc", event=event)


# ── Async iterator mock for TypedConsumer ──────────────────────────────


class _MockTypedIter:
    """Fake async iterator yielding (str, model, KafkaMessage) tuples."""

    def __init__(self, *items: tuple[str, BaseModel, KafkaMessage]) -> None:
        self._items = list(items)
        self._idx = 0
        self.committed: list[KafkaMessage] = []
        self.closed = False

    def __aiter__(self) -> _MockTypedIter:
        return self

    async def __anext__(self) -> tuple[str, BaseModel, KafkaMessage]:
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._idx]
        self._idx += 1
        return item

    async def commit(self, msg: KafkaMessage) -> None:
        self.committed.append(msg)


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — dispatch by event_type
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dispatches_to_correct_handler() -> None:
    """Two handlers for different event types → each dispatched for its own type."""
    lifecycle_model = _lifecycle(LifecycleEventType.READY)
    request_model = ServiceRequestEvent(service=ServiceRequestType.REQUEST_CASH_BALANCE)
    raw = _raw_msg()

    lifecycle_called = False
    request_called = False

    async def on_lifecycle(_m: LifecycleEvent, _r: KafkaMessage) -> None:
        nonlocal lifecycle_called
        lifecycle_called = True

    async def on_request(_m: ServiceRequestEvent, _r: KafkaMessage) -> None:
        nonlocal request_called
        request_called = True

    router = EventRouter("t", _settings(), group_suffix="t1")
    router.on(LifecycleEvent, on_lifecycle)
    router.on(ServiceRequestEvent, on_request)

    mock_iter = _MockTypedIter(
        (str(EventType.SERVICE_LIFECYCLE), lifecycle_model, raw),
        (str(EventType.SERVICE_REQUEST), request_model, raw),
    )
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.run()

    assert lifecycle_called
    assert request_called


@pytest.mark.asyncio
async def test_filter_fn_skips_non_matching() -> None:
    """filter_fn that returns False → handler NOT called."""
    called = False

    async def handler(_m: LifecycleEvent, _r: KafkaMessage) -> None:
        nonlocal called
        called = True

    router = EventRouter("t", _settings(), group_suffix="t2")
    router.on(LifecycleEvent, handler, filter_fn=lambda _m, _r: False)

    mock_iter = _MockTypedIter(
        (str(EventType.SERVICE_LIFECYCLE), _lifecycle(LifecycleEventType.READY), _raw_msg()),
    )
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.run()

    assert not called


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — auto_commit
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_auto_commit_true_commits_after_handler() -> None:
    """auto_commit=True → commit() called after successful handler."""
    raw = _raw_msg(offset=10)

    async def handler(_m: LifecycleEvent, _r: KafkaMessage) -> None:
        pass

    router = EventRouter("t", _settings(), group_suffix="t3", auto_commit=True)
    router.on(LifecycleEvent, handler)

    mock_iter = _MockTypedIter(
        (str(EventType.SERVICE_LIFECYCLE), _lifecycle(LifecycleEventType.READY), raw),
    )
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.run()

    assert len(mock_iter.committed) == 1
    assert mock_iter.committed[0].offset == 10


@pytest.mark.asyncio
async def test_auto_commit_false_does_not_commit() -> None:
    """auto_commit=False → commit() NOT called automatically."""
    raw = _raw_msg()

    async def handler(_m: LifecycleEvent, _r: KafkaMessage) -> None:
        pass

    router = EventRouter("t", _settings(), group_suffix="t4", auto_commit=False)
    router.on(LifecycleEvent, handler)

    mock_iter = _MockTypedIter(
        (str(EventType.SERVICE_LIFECYCLE), _lifecycle(LifecycleEventType.READY), raw),
    )
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.run()

    assert len(mock_iter.committed) == 0


@pytest.mark.asyncio
async def test_manual_commit_with_auto_commit_false() -> None:
    """auto_commit=False + handler calls router.commit() → offset committed."""
    raw = _raw_msg(offset=5)

    async def handler(_m: LifecycleEvent, _r: KafkaMessage) -> None:
        await router.commit(raw)

    router = EventRouter("t", _settings(), group_suffix="t5", auto_commit=False)
    router.on(LifecycleEvent, handler)

    mock_iter = _MockTypedIter(
        (str(EventType.SERVICE_LIFECYCLE), _lifecycle(LifecycleEventType.READY), raw),
    )
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.run()

    assert len(mock_iter.committed) == 1
    assert mock_iter.committed[0].offset == 5


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — handler exception → no commit
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_handler_exception_skips_commit() -> None:
    """Handler raises → exception swallowed, commit NOT called."""
    raw = _raw_msg()

    async def failing_handler(_m: LifecycleEvent, _r: KafkaMessage) -> None:
        raise RuntimeError("boom")

    router = EventRouter("t", _settings(), group_suffix="t6", auto_commit=True)
    router.on(LifecycleEvent, failing_handler)

    mock_iter = _MockTypedIter(
        (str(EventType.SERVICE_LIFECYCLE), _lifecycle(LifecycleEventType.READY), raw),
    )
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.run()  # should not raise

    assert len(mock_iter.committed) == 0  # no commit on failure


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — on_error callback
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_on_error_callback_passed_to_typed_consumer() -> None:
    """EventRouter passes on_error through to TypedConsumer constructor."""
    on_error = AsyncMock()

    router = EventRouter("t", _settings(), group_suffix="t7", on_error=on_error)
    router.on(LifecycleEvent, AsyncMock())

    with patch("tradingcz.sdk.messaging.router.TypedConsumer") as mock_tc:
        mock_tc.return_value = _MockTypedIter()
        await router.run()

    # Verify TypedConsumer was created with on_error
    _call_kwargs = mock_tc.call_args.kwargs
    assert _call_kwargs["on_error"] is on_error


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    """Calling start() twice only creates one background task."""
    router = EventRouter("t", _settings(), group_suffix="t8")
    router.on(LifecycleEvent, AsyncMock())

    mock_iter = _MockTypedIter()
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.start()
        task1 = router._run_task
        await router.start()
        task2 = router._run_task

    assert task1 is task2  # same task, not recreated
    await router.close()


@pytest.mark.asyncio
async def test_close_cancels_task() -> None:
    """close() cancels the background task and sets _consumer to None."""
    router = EventRouter("t", _settings(), group_suffix="t9")
    router.on(LifecycleEvent, AsyncMock())

    mock_iter = _MockTypedIter()
    with patch("tradingcz.sdk.messaging.router.TypedConsumer", return_value=mock_iter):
        await router.start()
        assert router._run_task is not None
        await router.close()

    assert router._run_task is None
    assert router._consumer is None
