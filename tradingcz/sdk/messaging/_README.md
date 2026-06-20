# messaging — Layer 3: Messaging Patterns

Ready-to-use messaging patterns built on [typed](../typed/_README.md) (Layer 2)
and [transport](../transport/_README.md) (Layer 1).

## Architecture position

```
┌─────────────────────────────────────────┐
│  ServiceApp                             │  ← Layer 4: Application
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: THIS PACKAGE
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: Transport
└─────────────────────────────────────────┘
```

## What this layer is

Layer 3 provides **complete, ready-to-use messaging patterns**.  Each class
solves one well-defined communication problem.  Application code imports a
class, configures it, and uses it — no Kafka wiring, no serialization, no
offset management.

Layer 3 classes use Layer 2 (`TypedProducer` / `TypedConsumer`) internally —
they never touch raw bytes or Kafka consumers directly.

## Components

| Class | Solves | Key API |
|-------|--------|---------|
| `EventRouter` | Route incoming messages to async handlers by `event_type` | `router.on(type, model, handler)` |
| `RequestReply` | Send a typed request, await a correlated typed response | `await rr.request(req, response_type=…)` |
| `FireAndForget` | Send a typed message, no response expected | `await faf.send(msg, event_type=…, event_id=…)` |
| `ReplayConsumer` | Replay a topic from the beginning until a sentinel | `async for … in consumer.replay(types, until=…)` |
| `HealthPublisher` | Emit `INITIALIZING` / `READY` / `HEARTBEAT` / `DOWN` | `await health.initializing()` / `ready()` / `down()` |

> **TypedProducer, TypedConsumer** are Layer 2 — see [typed/_README.md](../typed/_README.md).

## When to use each

| You want to… | Use |
|-------------|-----|
| Consume messages and dispatch to handlers by type | `EventRouter` |
| Send a request and await a response (correlated by `event_id`) | `RequestReply` |
| Fire off a message and forget about it | `FireAndForget` |
| Rebuild in-memory state from the event log on startup | `ReplayConsumer` |
| Let the platform know your service is alive | `HealthPublisher` (in ``tradingcz.sdk.health``) |

## Common patterns

### EventRouter — typed dispatch with filtering

**Handler registration is a direct call, not a decorator.**  ``handler`` is a
required positional argument — ``@router.on(...)`` would fail at import time.

```python
from tradingcz.sdk.messaging import EventRouter

router = EventRouter(
    topic,
    settings,
    group_suffix="worker",          # required — isolates consumer groups
    auto_commit=True,               # default: commit after handler success
    on_error=log_bad_message,       # optional: callback for undispatchable msgs
    auto_offset_reset="earliest",   # optional: override KafkaSettings default
    poll_timeout_ms=500,            # optional: override consumer poll timeout
    batch_size=50,                  # optional: override consumer batch size
)

# ── Handler signature: async (model, raw) ──────────────────────────
async def on_data_request(model: DataRequest, raw: KafkaMessage) -> None:
    """Process a data request — model is already parsed, raw has metadata."""
    source_app = raw.headers.get("source_app", "")
    result = await fetch_data(model)
    await svc.publish_event(result, message_type=EventType.DATA_READY, event_id=model.event_id)

# Register — direct call (NOT a decorator)
router.on(
    EventType.DATA_REQUEST,
    DataRequest,
    on_data_request,
    spawn_task=True,                # spawn asyncio.Task → router not blocked
)
```

**All `on()` parameters:**

| Param | Required | Default | Purpose |
|-------|----------|---------|---------|
| `msg_type` | ✅ | — | `EventType` this handler subscribes to |
| `model_class` | ✅ | — | Pydantic model for deserialization |
| `handler` | ✅ | — | `async (model, raw) -> None` |
| `filter_fn` | — | `None` | `(model, raw) -> bool` — handler called only when `True` |
| `spawn_task` | — | `False` | `True` = `asyncio.Task` per message (for slow handlers) |

**Handler signature:**

```python
async def handler_name(model: SpecificModel, raw: KafkaMessage) -> None:
    ...
```

- `model` — parsed Pydantic instance, ready to use
- `raw` — original `KafkaMessage` with `.headers`, `.offset`, `.partition`, `.key`

**Filtering example:**

```python
# Only process requests for this broker
def is_my_broker(model: DataRequest, raw: KafkaMessage) -> bool:
    return model.broker == Broker.ALPACA

router.on(EventType.DATA_REQUEST, DataRequest, on_data_request,
          filter_fn=is_my_broker, spawn_task=True)
```

**Manual commit (at-least-once with side effects):**

```python
router = EventRouter(topic, settings, group_suffix="worker", auto_commit=False)

async def on_execution(model: ExecutionRequestEvent, raw: KafkaMessage) -> None:
    await db.save(model)           # persist first
    await router.commit(raw)       # commit offset AFTER side effect
    await submit_to_broker(model)  # fire-and-forget — safe to lose

router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent, on_execution)
```

**Lifecycle:**

```python
# Option 1: async with (auto start/close)
async with EventRouter(topic, settings, group_suffix="worker") as router:
    router.on(EventType.DATA_REQUEST, DataRequest, on_data_request)
    # start() called on enter, close() on exit

# Option 2: manual
router = EventRouter(topic, settings, group_suffix="worker")
router.on(EventType.DATA_REQUEST, DataRequest, on_data_request)
await router.start()
await svc.wait_for_shutdown()
await router.close()
```

> ``on()`` is chainable — returns ``self``.  To make ``@router.on(...)`` work
> as a decorator, ``handler`` would need to become optional and return a
> decorator closure.  This is intentionally NOT supported — the direct-call
> pattern is explicit and easier to type-check.

### Request/response (market data clients)

```python
from tradingcz.sdk.messaging import RequestReply

async with RequestReply(producer, topic, settings, "my-svc", group_suffix="rr") as rr:
    rr.register_type(EventType.DATA_READY, DataReady)
    response = await rr.request(request, response_type=DataReady, timeout=15.0)
```

### Fire-and-forget (signals, lifecycle events)

```python
from tradingcz.sdk.messaging import FireAndForget

faf = FireAndForget(producer, topic, service_id="risk")
await faf.send(signal, event_type=EventType.TRADING_SIGNAL, event_id="evt-001")
```

### Startup recovery (ingestion, risk)

```python
from tradingcz.sdk.messaging import ReplayConsumer

# INITIALIZING sentinel is published automatically by ServiceApp.start().
# Replay until your own INITIALIZING:
consumer = ReplayConsumer(topic, settings)
async for msg_type, model, raw in consumer.replay(
    types={str(EventType.DATA_REQUEST): DataRequest, …},
    until=lambda mt, m: (
        mt == str(EventType.SERVICE_LIFECYCLE)
        and m.service_id == svc.service_id
        and m.event == LifecycleEventType.INITIALIZING
    ),
):
    reconstruct_state(msg_type, model, raw.headers)

# READY is published automatically by ServiceApp.start() after
# _on_after_initializing() completes.  Override that hook for
# custom init (e.g., recovery).
```
