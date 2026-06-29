"""Unit tests for EventRouter — handler registration, dispatch, and filtering."""
# pylint: disable=protected-access

from __future__ import annotations

import pytest

from tradingcz.sdk.messaging.router import EventRouter
from tradingcz.sdk.models.enums.event import (
    EventType,
    LifecycleEventType,
    ServiceRequestType,
)
from tradingcz.sdk.models.events.lifecycle_event import LifecycleEvent
from tradingcz.sdk.models.events.service_request_event import ServiceRequestEvent
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _settings() -> KafkaSettings:
    return KafkaSettings(bootstrap_servers="localhost:9092", consumer_group="test-router")


def _msg(offset: int = 0, key: str = "", headers: dict[str, str] | None = None) -> KafkaMessage:
    return KafkaMessage(
        payload=b"{}",
        topic="test-topic",
        partition=0,
        offset=offset,
        key=key,
        headers=headers or {},
    )


class _FakeConsumer:
    """Fake async iterator that yields pre-canned (msg_type, model, raw) tuples."""

    def __init__(self, *items: tuple[str, object | None, KafkaMessage]) -> None:
        self._items = list(items)
        self._idx = 0
        self.committed: list[KafkaMessage] = []

    def __aiter__(self) -> _FakeConsumer:
        return self

    async def __anext__(self) -> tuple[str, object | None, KafkaMessage]:
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._idx]
        self._idx += 1
        return item

    async def commit(self, msg: KafkaMessage) -> None:
        self.committed.append(msg)


# ── assert helper ──────────────────────────────────────────────────────

async def _run_router(router: EventRouter, fake: _FakeConsumer) -> None:
    """Run the router with a fake consumer, stopping after all messages consumed.

    Mirrors the dispatch logic from :meth:`EventRouter.run` but uses a
    pre-canned fake consumer instead of a real TypedConsumer.
    """
    router._consumer = fake  # type: ignore[assignment]
    async for msg_type, model, raw in fake:
        if model is None:
            continue
        reg = router._handlers.get(msg_type)
        if reg is None:
            continue  # unregistered type — silently ignored
        if reg.filter_fn is not None and not reg.filter_fn(model, raw):  # type: ignore[arg-type]
            continue
        await router._dispatch(reg, model, raw)


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEventRouterRegistration:
    """Registration tests — pure unit, no async needed."""

    def test_duplicate_registration_raises(self) -> None:
        """Registering same EventType twice raises ValueError."""
        router = EventRouter("t", _settings(), group_suffix="dup")

        async def handler(_m: LifecycleEvent, _r: KafkaMessage) -> None:
            pass

        router.on(LifecycleEvent, handler)
        with pytest.raises(ValueError, match="Handler already registered"):
            router.on(LifecycleEvent, handler)

    def test_different_event_types_ok(self) -> None:
        """Different EventTypes can be registered without conflict."""
        router = EventRouter("t", _settings(), group_suffix="multi")

        async def h1(_m: LifecycleEvent, _r: KafkaMessage) -> None:
            pass

        async def h2(_m: ServiceRequestEvent, _r: KafkaMessage) -> None:
            pass

        router.on(LifecycleEvent, h1)
        router.on(ServiceRequestEvent, h2)
        # No exception → pass


class TestEventRouterDispatch:
    """Dispatch tests — fake consumer, no Kafka needed."""

    @pytest.mark.asyncio
    async def test_registered_type_dispatched_unregistered_ignored(self) -> None:
        """Only messages matching a registered handler are dispatched."""
        router = EventRouter("t", _settings(), group_suffix="disp", auto_commit=False)

        received: list[LifecycleEvent] = []

        async def lifecycle_handler(model: LifecycleEvent, _raw: KafkaMessage) -> None:
            received.append(model)

        router.on(LifecycleEvent, lifecycle_handler)

        # Two messages: one matching (SERVICE_LIFECYCLE), one unmatched (SERVICE_REQUEST)
        matched_event = LifecycleEvent(service_id="svc1", event=LifecycleEventType.READY)
        unmatched_event = ServiceRequestEvent(service=ServiceRequestType.REQUEST_CASH_BALANCE)

        raw1 = _msg(offset=0, key="k1")
        raw2 = _msg(offset=1, key="k2")

        fake = _FakeConsumer(
            (str(EventType.SERVICE_LIFECYCLE), matched_event, raw1),
            (str(EventType.SERVICE_REQUEST), unmatched_event, raw2),
        )

        await _run_router(router, fake)

        assert len(received) == 1
        assert received[0].service_id == "svc1"
        assert received[0].event == LifecycleEventType.READY

    @pytest.mark.asyncio
    async def test_filter_fn_matches_by_key(self) -> None:
        """Filter function receives the model and raw KafkaMessage — test key-based filtering."""
        router = EventRouter("t", _settings(), group_suffix="filter", auto_commit=False)

        received: list[LifecycleEvent] = []

        async def lifecycle_handler(model: LifecycleEvent, _raw: KafkaMessage) -> None:
            received.append(model)

        def only_key_a(_model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return raw.key == "key-a"

        router.on(
            LifecycleEvent,
            lifecycle_handler,
            filter_fn=only_key_a,
        )

        # Two messages of same type, different keys
        event1 = LifecycleEvent(service_id="svc-a", event=LifecycleEventType.READY)
        event2 = LifecycleEvent(service_id="svc-b", event=LifecycleEventType.HEARTBEAT)

        raw_a = _msg(offset=0, key="key-a")
        raw_b = _msg(offset=1, key="key-b")

        fake = _FakeConsumer(
            (str(EventType.SERVICE_LIFECYCLE), event1, raw_a),
            (str(EventType.SERVICE_LIFECYCLE), event2, raw_b),
        )

        await _run_router(router, fake)

        assert len(received) == 1
        assert received[0].service_id == "svc-a"
        assert received[0].event == LifecycleEventType.READY

    @pytest.mark.asyncio
    async def test_filter_fn_matches_by_header(self) -> None:
        """Filter function can inspect Kafka headers on the raw message."""
        router = EventRouter("t", _settings(), group_suffix="filter-hdr", auto_commit=False)

        received: list[LifecycleEvent] = []

        async def lifecycle_handler(model: LifecycleEvent, _raw: KafkaMessage) -> None:
            received.append(model)

        def only_alpha_source(_model: LifecycleEvent, raw: KafkaMessage) -> bool:
            return raw.headers.get("source_app") == "alpha"

        router.on(
            LifecycleEvent,
            lifecycle_handler,
            filter_fn=only_alpha_source,
        )

        event = LifecycleEvent(service_id="svc", event=LifecycleEventType.READY)

        raw_alpha = _msg(offset=0, headers={"source_app": "alpha"})
        raw_beta = _msg(offset=1, headers={"source_app": "beta"})

        fake = _FakeConsumer(
            (str(EventType.SERVICE_LIFECYCLE), event, raw_alpha),
            (str(EventType.SERVICE_LIFECYCLE), event, raw_beta),
        )

        await _run_router(router, fake)

        assert len(received) == 1
        assert raw_alpha.headers.get("source_app") == "alpha"
