# typed — Layer 2: Typed Wrappers

Typed send/receive on top of the transport layer (L1).  Adds Pydantic model serialization
and header-based dispatch.  Sits between raw transport (L1) and messaging patterns (L3).

## Architecture position

```text
┌─────────────────────────────────────────┐
│  ServiceApp / TradingApp                │  ← Layer 4: Application
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: THIS PACKAGE
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: Transport
└─────────────────────────────────────────┘
```text

## Components

| Class | Sends? | Receives? | Lifecycle |
| ------- | -------- | ----------- | ----------- |
| `TypedProducer` | ✅ Pydantic models → Kafka | ❌ | `async with` (auto-flush) or manual `flush()` |
| `TypedConsumer` | ❌ | ✅ header-based dispatch → typed models | `async for` (auto-close + auto-commit) |

## TypedProducer

Publish typed Pydantic models via a shared `TransportProducer`.  One `TransportProducer` per process — `TypedProducer` instances share it.

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
```text

## TypedConsumer

Header-based typed dispatch from a shared multi-type Kafka topic.
Iterate directly — one yield shape: ``(msg_type, model, raw)``.

```python
from tradingcz.sdk.typed import TypedConsumer
from tradingcz.sdk.transport import KafkaSettings
from tradingcz.sdk.models.enums.event import EventType

settings = KafkaSettings(consumer_group="my-service")

# Auto-commit (default): offset committed after each successful yield
async for msg_type, model, raw in TypedConsumer("dev-events", settings, types={
    EventType.DATA_REQUEST: DataRequest,
    EventType.SERVICE_LIFECYCLE: LifecycleEvent,
}, group_suffix="alerts"):
    if msg_type == EventType.DATA_REQUEST:
        await handle_request(model)

# Manual commit: handler controls when offset is committed
consumer = TypedConsumer("dev-events", settings, types={...}, group_suffix="signals", auto_commit=False)
async for msg_type, model, raw in consumer:
    await db.save(model)          # persist first
    await consumer.commit(raw)    # then commit offset

# Start from beginning (replay history):
consumer = TypedConsumer("dev-events", settings, types={...}, group_suffix="replay", auto_offset_reset="earliest")
```text

| Parameter | Required | Default | Notes |
| ----------- | ---------- | --------- | ------- |
| `topic` | ✅ | — | Kafka topic name |
| `settings` | ✅ | — | `KafkaSettings` instance |
| `types` | ✅ | — | `{event_type_str: PydanticModel}` mapping |
| `group_suffix` | ✅ | — | Must be unique per consumer on same topic |
| `auto_commit` | — | `True` | Commit after each yield |
| `auto_offset_reset` | — | `None` (uses `KafkaSettings.auto_offset_reset`) | `"earliest"` = replay, `"latest"` = new only |
| `poll_timeout_ms` | — | `None` (uses `KafkaSettings.consumer_poll_timeout_ms`) | Longer timeouts reduce CPU spin on low-volume topics |
| `batch_size` | — | `None` (uses `KafkaSettings.consumer_batch_size`) | Larger batches improve throughput on high-volume topics |
| `on_error` | — | `None` | Callback for undispatchable messages |
