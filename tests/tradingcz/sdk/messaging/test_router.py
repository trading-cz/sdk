"""Unit tests for EventRouter."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from tradingcz.sdk.messaging.router import EventRouter
from tradingcz.sdk.models.enums.event import EventType, LifecycleEventType
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.transport.headers import Header
from tradingcz.sdk.transport.message import KafkaMessage


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


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


def _mock_session(*messages: KafkaMessage) -> MagicMock:
    """Create a mock ReceiveSession yielding *messages* with tracked commits."""
    commits: list[KafkaMessage] = []

    class _Session:
        def __init__(self) -> None:
            self._commits: list[KafkaMessage] = commits

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not hasattr(self, '_idx'):
                self._idx = 0
            if self._idx >= len(messages):
                raise StopAsyncIteration
            msg = messages[self._idx]
            self._idx += 1
            return msg

        async def commit(self, msg: KafkaMessage) -> None:
            commits.append(msg)

    session = _Session()
    return session  # type: ignore[return-value]


def _was_committed(session: MagicMock, msg: KafkaMessage) -> bool:
    """Check whether *msg* was committed via the mock session."""
    return msg in session._commits  # type: ignore[attr-defined]


def _setup_channel(*messages: KafkaMessage) -> MagicMock:
    """Create a mock KafkaChannel that returns a mock ReceiveSession."""
    channel = MagicMock()
    channel.name = "events"
    session = _mock_session(*messages)
    channel.receive = MagicMock(return_value=session)
    return channel


# ═════════════════════════════════════════════════════════════════════════════
# Test 1: Success scenario — valid message dispatched to handler
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterSuccess:
    """Happy-path scenarios for EventRouter dispatch."""

    @pytest.mark.asyncio
    async def test_dispatches_valid_message_to_handler(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="ingestion", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=42)
        channel = _setup_channel(kafka_msg)

        handler_calls: list[tuple[LifecycleEvent, KafkaMessage]] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            handler_calls.append((model, raw))

        router = EventRouter(channel)
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
        channel = _setup_channel(kafka_msg)

        match_called = False
        other_called = False

        async def match_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal match_called
            match_called = True

        async def other_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal other_called
            other_called = True

        router = EventRouter(channel)
        router.on(EventType.DATA_REQUEST, LifecycleEvent, other_handler)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, match_handler)

        await router.run()

        assert match_called
        assert not other_called

    @pytest.mark.asyncio
    async def test_spawn_task_handler_is_called(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="executor", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=1)
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True
            await asyncio.sleep(0.01)

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, spawn_task=True)

        await router.run()
        await asyncio.sleep(0.05)
        assert handler_called

    @pytest.mark.asyncio
    async def test_filter_fn_blocks_handler(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=1)
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        def deny_all(model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return False

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, filter_fn=deny_all)

        await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_filter_fn_allows_handler(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=1)
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        def allow_all(model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return True

        router = EventRouter(channel)
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
        kafka_msg = _make_raw_msg(
            payload=b"this is not valid json {{{",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=99,
        )
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_payload_missing_required_fields(self) -> None:
        incomplete_payload = json.dumps({"extra_field": "value"}).encode()
        kafka_msg = _make_raw_msg(
            payload=incomplete_payload,
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=100,
        )
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_message_with_no_event_type_header(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(payload=payload, msg_type="", offset=101)
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_message_with_unregistered_event_type(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(
            payload=payload,
            msg_type=str(EventType.DATA_REQUEST),
            offset=102,
        )
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_skips_empty_payload(self) -> None:
        kafka_msg = _make_raw_msg(
            payload=b"",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=103,
        )
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called

    @pytest.mark.asyncio
    async def test_continues_after_parse_failure(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="valid-service", event=LifecycleEventType.DOWN)
        valid_msg = _make_msg(lifecycle_event, offset=2)
        invalid_msg = _make_raw_msg(
            payload=b"garbage",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=1,
        )
        channel = _setup_channel(invalid_msg, valid_msg)

        handler_calls: list[tuple[LifecycleEvent, KafkaMessage]] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            handler_calls.append((model, raw))

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(handler_calls) == 1
        assert handler_calls[0][0].service_id == "valid-service"
        assert handler_calls[0][1].offset == 2


# ═════════════════════════════════════════════════════════════════════════════
# Test 3: Commit behaviour — via ReceiveSession through TypedConsumer
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterCommit:
    """Offset commit semantics — auto_commit, manual, failure."""

    @pytest.mark.asyncio
    async def test_auto_commit_true_commits_after_success(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=7)
        channel = _setup_channel(kafka_msg)

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel, auto_commit=True)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert handler_called
        session = channel.receive.return_value
        assert _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_auto_commit_true_does_not_commit_on_handler_failure(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=8)
        channel = _setup_channel(kafka_msg)

        async def failing_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            raise RuntimeError("simulated handler crash")

        router = EventRouter(channel, auto_commit=True)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, failing_handler)

        await router.run()

        session = channel.receive.return_value
        assert not _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_auto_commit_false_does_not_auto_commit(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=9)
        channel = _setup_channel(kafka_msg)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass  # does NOT call router.commit()

        router = EventRouter(channel, auto_commit=False)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        session = channel.receive.return_value
        assert not _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_manual_commit_via_router_commit(self) -> None:
        """Handler can explicitly commit by calling ``await router.commit(raw)``."""
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=10)
        channel = _setup_channel(kafka_msg)

        # Need access to router inside handler — use nonlocal
        committed: list[KafkaMessage] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            await router.commit(raw)
            committed.append(raw)

        router = EventRouter(channel, auto_commit=False)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(committed) == 1
        session = channel.receive.return_value
        assert _was_committed(session, kafka_msg)

    @pytest.mark.asyncio
    async def test_spawn_task_auto_commits_after_task_completes(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=11)
        channel = _setup_channel(kafka_msg)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            await asyncio.sleep(0.01)

        router = EventRouter(channel, auto_commit=True)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler, spawn_task=True)

        await router.run()
        await asyncio.sleep(0.1)

        session = channel.receive.return_value
        assert _was_committed(session, kafka_msg)


# ═════════════════════════════════════════════════════════════════════════════
# Test 4: on_error callback
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterOnError:
    """on_error callback — invoked for undispatchable messages."""

    @pytest.mark.asyncio
    async def test_on_error_called_for_invalid_json(self) -> None:
        kafka_msg = _make_raw_msg(
            payload=b"not json",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=200,
        )
        channel = _setup_channel(kafka_msg)

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 1
        assert errors[0].offset == 200

    @pytest.mark.asyncio
    async def test_on_error_called_for_missing_event_type_header(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(payload=payload, msg_type="", offset=201)
        channel = _setup_channel(kafka_msg)

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 1
        assert errors[0].offset == 201

    @pytest.mark.asyncio
    async def test_on_error_called_for_unregistered_event_type(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(
            payload=payload,
            msg_type=str(EventType.DATA_REQUEST),
            offset=202,
        )
        channel = _setup_channel(kafka_msg)

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 1
        assert errors[0].offset == 202

    @pytest.mark.asyncio
    async def test_on_error_not_called_for_valid_message(self) -> None:
        lifecycle_event = LifecycleEvent(service_id="test", event=LifecycleEventType.UP)
        kafka_msg = _make_msg(lifecycle_event, offset=203)
        channel = _setup_channel(kafka_msg)

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_on_error_exception_does_not_crash_router(self) -> None:
        invalid_msg = _make_raw_msg(
            payload=b"bad",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=204,
        )
        lifecycle_event = LifecycleEvent(service_id="valid", event=LifecycleEventType.DOWN)
        valid_msg = _make_msg(lifecycle_event, offset=205)
        channel = _setup_channel(invalid_msg, valid_msg)

        error_count = 0

        async def on_error(raw: KafkaMessage) -> None:
            nonlocal error_count
            error_count += 1
            if error_count == 1:
                raise RuntimeError("simulated on_error crash")

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert error_count >= 1
        assert handler_called
