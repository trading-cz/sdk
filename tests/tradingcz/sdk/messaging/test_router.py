"""Unit tests for EventRouter."""

import asyncio
import json
from unittest.mock import patch

import pytest

from tradingcz.sdk.messaging.router import EventRouter
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.transport.headers import Header
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.message import KafkaMessage

PATCH_TARGET = "tradingcz.sdk.typed.typed_consumer.TransportConsumer"


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _settings() -> KafkaSettings:
    return KafkaSettings(bootstrap_servers="localhost:9092", consumer_group="test")


def _make_msg(
    model: LifecycleEvent,
    *,
    offset: int = 0,
    msg_type: EventType = EventType.SERVICE_LIFECYCLE,
) -> KafkaMessage:
    payload = model.model_dump_json().encode()
    return KafkaMessage(
        payload=payload,
        key="",
        headers={Header.EVENT_TYPE: str(msg_type)},
        offset=offset,
        partition=0,
        topic="events",
    )


def _make_raw_msg(
    payload: bytes,
    msg_type: str = "",
    offset: int = 0,
) -> KafkaMessage:
    headers: dict[str, str] = {}
    if msg_type:
        headers[Header.EVENT_TYPE] = msg_type
    return KafkaMessage(
        payload=payload,
        key="",
        headers=headers,
        offset=offset,
        partition=0,
        topic="events",
    )


def _setup_consumer(*messages: KafkaMessage) -> object:
    """Create a fake async-iterable consumer yielding *messages* with tracked commits."""
    commits: list[KafkaMessage] = []

    class _MockConsumer:
        def __init__(self) -> None:
            self._commits: list[KafkaMessage] = commits

        def __aiter__(self) -> "_MockConsumer":
            self._idx = 0
            return self

        async def __anext__(self) -> KafkaMessage:
            if self._idx >= len(messages):
                raise StopAsyncIteration
            msg = messages[self._idx]
            self._idx += 1
            return msg

        async def commit(self, msg: KafkaMessage) -> None:
            commits.append(msg)

    return _MockConsumer()


def _was_committed(session: MagicMock, msg: KafkaMessage) -> bool:
    """Check whether *msg* was committed via the mock session."""
    return msg in session._commits  # type: ignore[attr-defined]


def _make_router(session: MagicMock, **kwargs: object) -> EventRouter:
    """Create an EventRouter with TransportConsumer patched to return *session*."""
    patcher = patch("PATCH_TARGET", return_value=session)
    patcher.start()
    # Stop patcher at test teardown — manually controlled for simplicity
    return EventRouter("events", _settings(), **kwargs)  # type: ignore[arg-type]


# ═════════════════════════════════════════════════════════════════════════════
# Test 1: Success scenario — valid message dispatched to handler
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterSuccess:
    """Happy-path scenarios for EventRouter dispatch."""

    @pytest.mark.asyncio
    async def test_dispatches_valid_message_to_handler(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="ingestion", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=42)
        session = _setup_consumer(kafka_msg)

        handler_calls: list[tuple[LifecycleEvent, KafkaMessage]] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            handler_calls.append((model, raw))

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert len(handler_calls) == 1
        model, raw = handler_calls[0]
        assert model.service_id == "ingestion"
        assert model.event == LifecycleEventType.UP
        assert raw.offset == 42

    @pytest.mark.asyncio
    async def test_dispatches_only_to_matching_msg_type(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="risk", event=LifecycleEventType.HEARTBEAT)
        kafka_msg = _make_msg(lifecycle_event, offset=10)
        session = _setup_consumer(kafka_msg)

        match_called = False
        other_called = False

        async def match_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal match_called
            match_called = True

        async def other_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal other_called
            other_called = True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.DATA_REQUEST, LifecycleEvent, other_handler)
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, match_handler)
            await router.run()

        assert match_called
        assert not other_called

    @pytest.mark.asyncio
    async def test_spawn_task_handler_is_called(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="executor", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=1)
        session = _setup_consumer(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True
            await asyncio.sleep(0.01)

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, spawn_task=True)
            await router.run()
            await asyncio.sleep(0.05)

        assert handler_called

    @pytest.mark.asyncio
    async def test_filter_fn_blocks_handler(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=1)
        session = _setup_consumer(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        def deny_all(model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return False

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, filter_fn=deny_all)
            await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_filter_fn_allows_handler(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=1)
        session = _setup_consumer(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        def allow_all(model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, filter_fn=allow_all)
            await router.run()

        assert handler_called


# ═════════════════════════════════════════════════════════════════════════════
# Test 2: Parsing/decoding failure — invalid payloads skipped silently
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterParseFailure:
    """Edge cases where parsing/decoding fails."""

    @pytest.mark.asyncio
    async def test_skips_invalid_json_payload(self) -> None:
        kafka_msg = _make_raw_msg(payload=b"not json {{{", msg_type=str(EventType.SERVICE_LIFECYCLE), offset=99)
        session = _setup_consumer(kafka_msg)
        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_payload_missing_required_fields(self) -> None:
        kafka_msg = _make_raw_msg(payload=json.dumps({"extra": "v"}).encode(), msg_type=str(EventType.SERVICE_LIFECYCLE), offset=100)
        session = _setup_consumer(kafka_msg)
        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_message_with_no_event_type_header(self) -> None:
        kafka_msg = _make_raw_msg(payload=b'{"x":1}', msg_type="", offset=101)
        session = _setup_consumer(kafka_msg)
        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_message_with_unregistered_event_type(self) -> None:
        kafka_msg = _make_raw_msg(payload=b'{"x":1}', msg_type=str(EventType.DATA_REQUEST), offset=102)
        session = _setup_consumer(kafka_msg)
        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_empty_payload(self) -> None:
        kafka_msg = _make_raw_msg(payload=b"", msg_type=str(EventType.SERVICE_LIFECYCLE), offset=103)
        session = _setup_consumer(kafka_msg)
        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_continues_after_parse_failure(self) -> None:
        valid_msg = _make_msg(LifecycleEvent(service_id="ok", event=LifecycleEventType.DOWN), offset=2)
        invalid_msg = _make_raw_msg(payload=b"garbage", msg_type=str(EventType.SERVICE_LIFECYCLE), offset=1)
        session = _setup_consumer(invalid_msg, valid_msg)
        calls: list[tuple[LifecycleEvent, KafkaMessage]] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            calls.append((model, raw))

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings())
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert len(calls) == 1
        assert calls[0][0].service_id == "ok"
        assert calls[0][1].offset == 2


# ═════════════════════════════════════════════════════════════════════════════
# Test 3: Commit behaviour
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterCommit:
    """Offset commit semantics — auto_commit, manual, failure."""

    @pytest.mark.asyncio
    async def test_auto_commit_true_commits_after_success(self) -> None:
        kafka_msg = _make_msg(LifecycleEvent(service_id="t", event=LifecycleEventType.UP), offset=7)
        session = _setup_consumer(kafka_msg)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings(), auto_commit=True)
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_auto_commit_true_does_not_commit_on_handler_failure(self) -> None:
        kafka_msg = _make_msg(LifecycleEvent(service_id="t", event=LifecycleEventType.UP), offset=8)
        session = _setup_consumer(kafka_msg)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            raise RuntimeError("boom")

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings(), auto_commit=True)
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_auto_commit_false_does_not_auto_commit(self) -> None:
        kafka_msg = _make_msg(LifecycleEvent(service_id="t", event=LifecycleEventType.UP), offset=9)
        session = _setup_consumer(kafka_msg)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings(), auto_commit=False)
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert not _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_manual_commit_via_router_commit(self) -> None:
        kafka_msg = _make_msg(LifecycleEvent(service_id="t", event=LifecycleEventType.UP), offset=10)
        session = _setup_consumer(kafka_msg)
        committed: list[KafkaMessage] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            await router.commit(raw)
            committed.append(raw)

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings(), auto_commit=False)
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)
            await router.run()

        assert len(committed) == 1
        assert _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_spawn_task_auto_commits_after_task_completes(self) -> None:
        kafka_msg = _make_msg(LifecycleEvent(service_id="t", event=LifecycleEventType.UP), offset=11)
        session = _setup_consumer(kafka_msg)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            await asyncio.sleep(0.02)

        with patch("PATCH_TARGET", return_value=session):
            router = EventRouter("events", _settings(), auto_commit=True)
            router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, spawn_task=True)
            await router.run()
            await asyncio.sleep(0.05)

        assert _was_committed(session, kafka_msg)
