# typed — Layer 2: Typed Wrappers

Typed send/receive on top of the transport layer (L1).  Adds Pydantic model serialization
and header-based dispatch.  Sits between raw transport (L1) and messaging patterns (L3).

## Architecture position

```text
┌─────────────────────────────────────────┐
│  Your App (direct wiring)               │  ← Layer 4: Application
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: THIS PACKAGE
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: Transport
└─────────────────────────────────────────┘
```

## Components

| Class | Sends? | Receives? | Dispatch | Yield type |
|---|---|---|---|---|
| `TypedProducer` | ✅ Pydantic → Kafka | ❌ | — | — |
| `TypedConsumer` | ❌ | ✅ | `event_type` header | `(str, BaseModel, raw)` |
| `SingleTypeConsumer[T]` | ❌ | ✅ | None (topic IS the type) | `(EventType, T, raw)` |

## When to use which consumer

| Scenario | Use |
|---|---|
| Topic has multiple types (event topic, historical) | `TypedConsumer` — dispatch by `event_type` |
| Topic has one type (per-type stream) or you only care about one | `SingleTypeConsumer` — generic `T` preserved |
| Need key/header filtering before parse | Both support `key_filter` / `header_filter` |

---

## TypedProducer

Publish typed Pydantic models via a shared `TransportProducer`.  One `TransportProducer`
per process — `TypedProducer` instances share it.

```python
from tradingcz.sdk.transport import TransportProducer, KafkaSettings
from tradingcz.sdk.typed import TypedProducer
from tradingcz.sdk.transport.kafka_header import KafkaHeader
from tradingcz.sdk.transport.kafka_key import KafkaKey

settings = KafkaSettings(consumer_group="my-service")
transport = TransportProducer(settings)  # one per process

# Auto-flush on exit (safe default):
async with TypedProducer(transport, "dev-events") as p:
    await p.send(signal, key=kafka_key, headers=kafka_headers)
# flushed automatically

# Manual batch — single flush for N messages:
p = TypedProducer(transport, "dev-events", auto_flush=False)
for signal in batch:
    await p.send(signal, key=kafka_key, headers=kafka_headers)
await p.flush()
```

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `producer` | ✅ | — | `TransportProducer` instance |
| `topic` | ✅ | — | Kafka topic name |
| `auto_flush` | — | `True` | Flush on `__aexit__` |

---

## TypedConsumer

Header-based typed dispatch from a shared multi-type Kafka topic.
Iterate directly — one yield shape: `(msg_type, model, raw)`.

`key_filter` and `header_filter` run **before** dispatch and JSON parsing,
saving CPU on high-volume topics.  Both must pass (AND logic).

```python
from tradingcz.sdk.typed import TypedConsumer
from tradingcz.sdk.transport import KafkaSettings

settings = KafkaSettings(consumer_group="my-service")

# Auto-commit (default): offset committed after each successful yield
async for msg_type, model, raw in TypedConsumer("dev-events", settings, types={
    "data_request": DataRequest,
    "service_lifecycle": LifecycleEvent,
}, group_suffix="alerts"):
    if msg_type == "data_request":
        await handle_request(model)

# Manual commit: handler controls when offset is committed
consumer = TypedConsumer("dev-events", settings, types={...},
    group_suffix="signals", auto_commit=False)
async for msg_type, model, raw in consumer:
    await db.save(model)
    await consumer.commit(raw)

# With pre-dispatch filters (saves CPU):
consumer = TypedConsumer("dev-events", settings, types={...},
    group_suffix="filtered",
    key_filter=lambda k: k.startswith("AAPL"),
    header_filter=lambda h: h.get("source_app") == "executor",
)

# Start from beginning (replay history):
consumer = TypedConsumer("dev-events", settings, types={...},
    group_suffix="replay", auto_offset_reset="earliest")
```

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `topic` | ✅ | — | Kafka topic name |
| `settings` | ✅ | — | `KafkaSettings` instance |
| `types` | ✅ | — | `{event_type_str: PydanticModel}` mapping |
| `group_suffix` | ✅ | — | Must be unique per consumer on same topic |
| `auto_commit` | — | `True` | Commit after each yield |
| `auto_offset_reset` | — | `None` | `"earliest"` = replay, `"latest"` = new only |
| `poll_timeout_ms` | — | `None` | Longer = less CPU on low-volume topics |
| `batch_size` | — | `None` | Larger = more throughput on high-volume topics |
| `on_error` | — | `None` | Callback for undispatchable messages |
| `key_filter` | — | `None` | `(str) -> bool`, before dispatch |
| `header_filter` | — | `None` | `(dict[str,str]) -> bool`, before dispatch |

---

## SingleTypeConsumer

Consume a single model type from a topic.  Wraps `TypedConsumer` internally
with a single-entry `types` dict derived from `model_type`.  Preserves the
concrete generic type `T` in the yield — no `BaseModel` cast needed.

```python
from tradingcz.sdk.typed import SingleTypeConsumer
from tradingcz.sdk.models.market.bar import Bar

consumer = SingleTypeConsumer(
    topic="dev-stock-stream-bars",
    settings=kafka_settings,
    model_type=Bar,               # ← explicit: every message parsed as Bar
    group_suffix="my-strategy",
    key_filter=lambda k: k in ("AAPL", "SPY"),
    header_filter=lambda h: h.get("event_id") == "abc-123",
)
async for event_type, bar, raw in consumer:
    # bar is Bar (not BaseModel) — type-safe
    if bar.close <= 0:
        continue
    await process(bar)
    await consumer.commit(raw)
```

`key_filter` and `header_filter` are delegated to the internal `TypedConsumer`
and run before dispatch/parse (AND logic, both must pass).

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `topic` | ✅ | — | Kafka topic name |
| `settings` | ✅ | — | `KafkaSettings` instance |
| `model_type` | ✅ | — | Pydantic model class (e.g. `Bar`) |
| `group_suffix` | ✅ | — | Must be unique per consumer on same topic |
| `key_filter` | — | `None` | `(str) -> bool`, before parse |
| `header_filter` | — | `None` | `(dict[str,str]) -> bool`, before parse |
| `auto_commit` | — | `True` | Commit after each yield |
| `auto_offset_reset` | — | `None` | `"earliest"` = replay |
| `poll_timeout_ms` | — | `None` | Longer = less CPU |
| `batch_size` | — | `None` | Larger = more throughput |
| `on_error` | — | `None` | Callback for unparseable messages |
