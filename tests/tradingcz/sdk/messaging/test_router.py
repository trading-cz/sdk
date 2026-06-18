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
    """Build a KafkaMessage with the given model as JSON payload."""
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
    """Build a KafkaMessage with raw bytes payload."""
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


# ═════════════════════════════════════════════════════════════════════════════
# Test 1: Success scenario — valid message dispatched to handler
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterSuccess:
    """Happy-path scenarios for EventRouter dispatch."""

    @pytest.mark.asyncio
    async def test_dispatches_valid_message_to_handler(self) -> None:
        """A valid message with matching message_type is parsed and dispatched."""
        # ── Arrange ───────────────────────────────────────────────────
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="ingestion",
            event=LifecycleEventType.UP,
        )
        kafka_msg = _make_msg(lifecycle_event, offset=42)

        async def mock_receive():  # async generator — yields 1 msg then stops
            yield kafka_msg

        channel.receive = mock_receive

        handler_calls: list[tuple[LifecycleEvent, KafkaMessage]] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            handler_calls.append((model, raw))

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        # ── Act ───────────────────────────────────────────────────────
        await router.run()

        # ── Assert ────────────────────────────────────────────────────
        assert len(handler_calls) == 1, "Handler should be called exactly once"
        model, raw = handler_calls[0]
        assert model.service_id == "ingestion"
        assert model.event == LifecycleEventType.UP
        assert raw.offset == 42
        assert raw.topic == "events"

    @pytest.mark.asyncio
    async def test_dispatches_only_to_matching_msg_type(self) -> None:
        """Only the handler registered for the matching EventType is called."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="risk",
            event=LifecycleEventType.HEARTBEAT,
        )
        kafka_msg = _make_msg(lifecycle_event, offset=10)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        match_called = False
        other_called = False

        async def match_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal match_called
            match_called = True

        async def other_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal other_called
            other_called = True

        router = EventRouter(channel)
        # Register handler for a DIFFERENT event type
        router.on(EventType.DATA_REQUEST, LifecycleEvent, other_handler)
        # Register handler for the CORRECT event type
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, match_handler)

        await router.run()

        assert match_called, "Matching handler should be called"
        assert not other_called, "Non-matching handler should NOT be called"

    @pytest.mark.asyncio
    async def test_spawn_task_handler_is_called(self) -> None:
        """Handler with spawn_task=True is called (as a task, not awaited inline)."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="executor",
            event=LifecycleEventType.UP,
        )
        kafka_msg = _make_msg(lifecycle_event, offset=1)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True
            # Simulate slow handler that would block inline dispatch
            await asyncio.sleep(0.01)

        router = EventRouter(channel)
        router.on(
            EventType.SERVICE_LIFECYCLE,
            LifecycleEvent,
            handler,
            spawn_task=True,
        )

        await router.run()

        # Allow the spawned task to complete before asserting
        await asyncio.sleep(0.05)
        assert handler_called, "Handler with spawn_task=True should be called"

    @pytest.mark.asyncio
    async def test_filter_fn_blocks_handler(self) -> None:
        """Handler is NOT called when filter_fn returns False."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test",
            event=LifecycleEventType.UP,
        )
        kafka_msg = _make_msg(lifecycle_event, offset=1)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        def deny_all(model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return False

        router = EventRouter(channel)
        router.on(
            EventType.SERVICE_LIFECYCLE,
            LifecycleEvent,
            handler,
            filter_fn=deny_all,
        )

        await router.run()

        assert not handler_called, (
            "Handler should NOT be called when filter_fn returns False"
        )

    @pytest.mark.asyncio
    async def test_filter_fn_allows_handler(self) -> None:
        """Handler IS called when filter_fn returns True."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test",
            event=LifecycleEventType.UP,
        )
        kafka_msg = _make_msg(lifecycle_event, offset=1)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        def allow_all(model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return True

        router = EventRouter(channel)
        router.on(
            EventType.SERVICE_LIFECYCLE,
            LifecycleEvent,
            handler,
            filter_fn=allow_all,
        )

        await router.run()

        assert handler_called, "Handler should be called when filter_fn returns True"


# ═════════════════════════════════════════════════════════════════════════════
# Test 2: Parsing/decoding failure — invalid payloads skipped silently
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterParseFailure:
    """Edge cases where parsing/decoding fails."""

    @pytest.mark.asyncio
    async def test_skips_invalid_json_payload(self) -> None:
        """A message with invalid JSON is silently skipped."""
        channel = MagicMock()
        channel.name = "events"

        kafka_msg = _make_raw_msg(
            payload=b"this is not valid json {{{",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=99,
        )

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called, (
            "Handler should NOT be called for invalid JSON payload"
        )

    @pytest.mark.asyncio
    async def test_skips_payload_missing_required_fields(self) -> None:
        """A message with valid JSON but missing required Pydantic fields is skipped."""
        channel = MagicMock()
        channel.name = "events"

        # Valid JSON but missing required fields for LifecycleEvent
        incomplete_payload = json.dumps({"extra_field": "value"}).encode()
        kafka_msg = _make_raw_msg(
            payload=incomplete_payload,
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=100,
        )

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called, (
            "Handler should NOT be called when required fields are missing"
        )

    @pytest.mark.asyncio
    async def test_skips_message_with_no_event_type_header(self) -> None:
        """A message without the event_type header is silently skipped."""
        channel = MagicMock()
        channel.name = "events"

        # Valid payload, but no event_type header
        lifecycle_event = LifecycleEvent(
            service_id="test",
            event=LifecycleEventType.UP,
        )
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(payload=payload, msg_type="", offset=101)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called, (
            "Handler should NOT be called when event_type header is missing"
        )

    @pytest.mark.asyncio
    async def test_skips_message_with_unregistered_event_type(self) -> None:
        """A message whose event_type is not registered is silently skipped."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test",
            event=LifecycleEventType.UP,
        )
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(
            payload=payload,
            msg_type=str(EventType.DATA_REQUEST),  # not registered
            offset=102,
        )

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        # Register only for SERVICE_LIFECYCLE, not DATA_REQUEST
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called, (
            "Handler should NOT be called for unregistered event_type"
        )

    @pytest.mark.asyncio
    async def test_skips_empty_payload(self) -> None:
        """An empty byte payload is silently skipped."""
        channel = MagicMock()
        channel.name = "events"

        kafka_msg = _make_raw_msg(
            payload=b"",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=103,
        )

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not handler_called, (
            "Handler should NOT be called for empty payload"
        )

    @pytest.mark.asyncio
    async def test_continues_after_parse_failure(self) -> None:
        """After a parse failure, subsequent valid messages are still processed."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="valid-service",
            event=LifecycleEventType.DOWN,
        )
        valid_msg = _make_msg(lifecycle_event, offset=2)
        invalid_msg = _make_raw_msg(
            payload=b"garbage",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=1,
        )

        async def mock_receive():
            yield invalid_msg   # first: parse failure → skipped
            yield valid_msg     # second: valid → dispatched

        channel.receive = mock_receive

        handler_calls: list[tuple[LifecycleEvent, KafkaMessage]] = []

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            handler_calls.append((model, raw))

        router = EventRouter(channel)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(handler_calls) == 1, (
            "Only the valid message should be dispatched; invalid one skipped"
        )
        assert handler_calls[0][0].service_id == "valid-service"
        assert handler_calls[0][1].offset == 2


# ═════════════════════════════════════════════════════════════════════════════
# Helpers for commit-aware messages
# ═════════════════════════════════════════════════════════════════════════════


def _attach_commit(msg: KafkaMessage) -> KafkaMessage:
    """Attach a mock ``_commit_fn`` to *msg* so ``raw.commit()`` works."""
    state: dict[str, bool] = {"committed": False}

    async def _mock_commit() -> None:
        state["committed"] = True

    object.__setattr__(msg, "_commit_fn", _mock_commit)
    object.__setattr__(msg, "_commit_state", state)
    return msg


def _was_committed(msg: KafkaMessage) -> bool:
    """Check whether ``msg.commit()`` was called."""
    state: dict[str, bool] | None = getattr(msg, "_commit_state", None)
    return state["committed"] if state else False


# ═════════════════════════════════════════════════════════════════════════════
# Test 3: Commit behaviour
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterCommit:
    """Offset commit semantics — auto_commit, manual, failure."""

    @pytest.mark.asyncio
    async def test_auto_commit_true_commits_after_success(self) -> None:
        """With auto_commit=True (default), offset is committed after handler."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        kafka_msg = _attach_commit(_make_msg(lifecycle_event, offset=7))

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        handler_called = False

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            nonlocal handler_called
            handler_called = True

        router = EventRouter(channel, auto_commit=True)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert handler_called
        assert _was_committed(kafka_msg), (
            "Offset should be committed after successful handler with auto_commit=True"
        )

    @pytest.mark.asyncio
    async def test_auto_commit_true_does_not_commit_on_handler_failure(self) -> None:
        """Offset is NOT committed when the handler raises an exception."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        kafka_msg = _attach_commit(_make_msg(lifecycle_event, offset=8))

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        async def failing_handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            raise RuntimeError("simulated handler crash")

        router = EventRouter(channel, auto_commit=True)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, failing_handler)

        await router.run()  # should NOT raise — exception is caught

        assert not _was_committed(kafka_msg), (
            "Offset should NOT be committed when handler raises"
        )

    @pytest.mark.asyncio
    async def test_auto_commit_false_does_not_auto_commit(self) -> None:
        """With auto_commit=False, offset is NOT committed automatically."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        kafka_msg = _attach_commit(_make_msg(lifecycle_event, offset=9))

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass  # does NOT call raw.commit()

        router = EventRouter(channel, auto_commit=False)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert not _was_committed(kafka_msg), (
            "Offset should NOT be committed when auto_commit=False "
            "and handler does not call raw.commit()"
        )

    @pytest.mark.asyncio
    async def test_manual_commit_via_raw_commit(self) -> None:
        """Handler can explicitly commit by calling ``await raw.commit()``."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        kafka_msg = _attach_commit(_make_msg(lifecycle_event, offset=10))

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            await raw.commit()  # explicit manual commit

        # auto_commit=False so only manual commit matters
        router = EventRouter(channel, auto_commit=False)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert _was_committed(kafka_msg), (
            "Offset should be committed when handler calls raw.commit()"
        )

    @pytest.mark.asyncio
    async def test_spawn_task_auto_commits_after_task_completes(self) -> None:
        """With spawn_task=True, commit happens after the spawned task finishes."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        kafka_msg = _attach_commit(_make_msg(lifecycle_event, offset=11))

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            await asyncio.sleep(0.01)  # simulate async work

        router = EventRouter(channel, auto_commit=True)
        router.on(
            EventType.SERVICE_LIFECYCLE,
            LifecycleEvent,
            handler,
            spawn_task=True,
        )

        await router.run()
        # Wait for the spawned dispatch task to complete
        await asyncio.sleep(0.1)

        assert _was_committed(kafka_msg), (
            "Offset should be committed after spawned task completes"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Test 4: on_error callback
# ═════════════════════════════════════════════════════════════════════════════


class TestEventRouterOnError:
    """on_error callback — invoked for undispatchable messages."""

    @pytest.mark.asyncio
    async def test_on_error_called_for_invalid_json(self) -> None:
        """on_error is called when payload fails Pydantic validation."""
        channel = MagicMock()
        channel.name = "events"

        kafka_msg = _make_raw_msg(
            payload=b"not json",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=200,
        )

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 1, "on_error should be called once for invalid JSON"
        assert errors[0].offset == 200

    @pytest.mark.asyncio
    async def test_on_error_called_for_missing_event_type_header(self) -> None:
        """on_error is called when event_type header is missing."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(payload=payload, msg_type="", offset=201)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 1, "on_error should be called for missing header"
        assert errors[0].offset == 201

    @pytest.mark.asyncio
    async def test_on_error_called_for_unregistered_event_type(self) -> None:
        """on_error is called when event_type is not registered."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        payload = lifecycle_event.model_dump_json().encode()
        kafka_msg = _make_raw_msg(
            payload=payload,
            msg_type=str(EventType.DATA_REQUEST),  # not registered
            offset=202,
        )

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        # Only register for SERVICE_LIFECYCLE, not DATA_REQUEST
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 1, (
            "on_error should be called for unregistered event_type"
        )
        assert errors[0].offset == 202

    @pytest.mark.asyncio
    async def test_on_error_not_called_for_valid_message(self) -> None:
        """on_error is NOT called when the message is dispatched successfully."""
        channel = MagicMock()
        channel.name = "events"

        lifecycle_event = LifecycleEvent(
            service_id="test", event=LifecycleEventType.UP
        )
        kafka_msg = _make_msg(lifecycle_event, offset=203)

        async def mock_receive():
            yield kafka_msg

        channel.receive = mock_receive

        errors: list[KafkaMessage] = []

        async def on_error(raw: KafkaMessage) -> None:
            errors.append(raw)

        async def handler(model: LifecycleEvent, raw: KafkaMessage) -> None:
            pass

        router = EventRouter(channel, on_error=on_error)
        router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent, handler)

        await router.run()

        assert len(errors) == 0, (
            "on_error should NOT be called for valid dispatched messages"
        )

    @pytest.mark.asyncio
    async def test_on_error_exception_does_not_crash_router(self) -> None:
        """An exception in on_error does not crash the router loop."""
        channel = MagicMock()
        channel.name = "events"

        invalid_msg = _make_raw_msg(
            payload=b"bad",
            msg_type=str(EventType.SERVICE_LIFECYCLE),
            offset=204,
        )
        lifecycle_event = LifecycleEvent(
            service_id="valid", event=LifecycleEventType.DOWN
        )
        valid_msg = _make_msg(lifecycle_event, offset=205)

        async def mock_receive():
            yield invalid_msg
            yield valid_msg

        channel.receive = mock_receive

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

        assert error_count >= 1, "on_error should have been called at least once"
        assert handler_called, (
            "Valid message should still be dispatched after on_error crashes"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Test 5: KafkaMessage.commit() contract
# ═════════════════════════════════════════════════════════════════════════════


class TestKafkaMessageCommit:
    """KafkaMessage.commit() behaviour."""

    @pytest.mark.asyncio
    async def test_commit_raises_runtime_error_for_manual_message(self) -> None:
        """commit() raises RuntimeError on a manually-constructed KafkaMessage."""
        msg = KafkaMessage(payload=b"{}")
        with pytest.raises(RuntimeError, match="Commit not available"):
            await msg.commit()

    @pytest.mark.asyncio
    async def test_commit_works_when_commit_fn_attached(self) -> None:
        """commit() works when _commit_fn is attached (as channel.receive() does)."""
        msg = KafkaMessage(payload=b"{}")
        committed = False

        async def mock_commit() -> None:
            nonlocal committed
            committed = True

        object.__setattr__(msg, "_commit_fn", mock_commit)
        await msg.commit()

        assert committed, "commit() should call the attached _commit_fn"
