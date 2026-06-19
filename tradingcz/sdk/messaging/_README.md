# messaging — Layer 3: Messaging Patterns

Higher-level messaging patterns built on [typed](../typed/_README.md) (Layer 2)
and [transport](../transport/_README.md) (Layer 1).

```
Layer 4: ServiceApp / TradingApp
Layer 3: EventRouter, RequestReply, FireAndForget  ← THIS PACKAGE
Layer 2: TypedProducer, TypedConsumer              (typed/)
Layer 1: KafkaChannel                               (transport/)
```

## Components

| Class | Pattern | Sends? | Receives? | Commits? |
|-------|---------|--------|-----------|----------|
| `FireAndForget` | One-way fire-and-forget | ✅ | ❌ | N/A |
| `RequestReply` | Request → await correlated response | ✅ | ✅ | Auto per msg |
| `EventRouter` | Typed handler dispatch by header | ❌ | ✅ | Configurable |
| `RecoveryReader` | One-time topic replay (fresh group) | ❌ | ✅ | N/A (ephemeral) |
| `HealthPublisher` | Periodic heartbeat (UP → DOWN) | ✅ | ❌ | N/A |

> **TypedProducer, TypedConsumer** are Layer 2 — see [typed/_README.md](../typed/_README.md).

---

---

## FireAndForget — send, no response expected

```python
from tradingcz.sdk.messaging import FireAndForget
from tradingcz.sdk.models.enums.event import EventType

faf = FireAndForget(channel, service_id="my-service")

# Send a typed model with auto-headers:
await faf.send_event(
    lifecycle_event,
    event_type=EventType.SERVICE_LIFECYCLE,
    event_id="evt-001",
)

# Send raw bytes with custom headers:
await faf.send(
    b'{"msg":"hello"}',
    key="my-key",
    headers={"event_type": "custom_type", "source_app": "test"},
)
```

---

## RequestReply — request/response by event_id

```python
import asyncio
from uuid import uuid4
from tradingcz.sdk.messaging import RequestReply
from tradingcz.sdk.models.events import DataRequest, DataReady
from tradingcz.sdk.models.enums.event import EventType, Broker, DataRequestType, MarketDataType
from tradingcz.sdk.models.enums.timeframe import Timeframe

async with RequestReply(channel, service_id="my-service") as rr:
    # Register expected response types (otherwise they're skipped):
    rr.register_type(EventType.DATA_READY, DataReady)

    request = DataRequest(
        event_id=uuid4(),
        type=DataRequestType.HISTORIC,
        broker=Broker.ALPACA,
        symbols=["AAPL"],
        data_type=MarketDataType.BARS,
        timeframe=Timeframe.D1,
    )

    # Send request, await correlated response (matched by event_id):
    response: DataReady = await rr.request(
        request,
        response_type=DataReady,
        timeout=15.0,
    )
    print(f"Got {response.record_count} records on {response.data_topic}")
```

> **Consumer group**: `{service_id}-{topic}-rr` — isolated from other consumers.
> **Commits**: Every message is committed after processing (match or skip).
> **Lifecycle**: Use as `async with` — listener starts on enter, cancelled on exit.

---

## EventRouter — typed dispatch by event_type header

```python
from tradingcz.sdk.messaging import EventRouter
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.message import KafkaMessage

router = EventRouter(channel)  # auto_commit=True by default, group_suffix="router"

# Register handlers — chainable:
@router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent, spawn_task=True)
async def on_execution(model: ExecutionRequestEvent, raw: KafkaMessage) -> None:
    await place_order(model)
    # Offset committed automatically after return (auto_commit=True).

@router.on(EventType.SERVICE_REQUEST, ServiceRequestEvent)
async def on_service(model: ServiceRequestEvent, raw: KafkaMessage) -> None:
    await handle_service(model)

# Block until cancelled:
await router.run()
```

### Commit modes

```python
# Mode 1 — Auto-commit (default): router commits after handler success
router = EventRouter(channel, auto_commit=True)

# Mode 2 — Manual commit: handler controls when offset is committed
router = EventRouter(channel, auto_commit=False)

@router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent)
async def on_request(model, raw):
    await db.save(model)      # persist first
    await raw.commit()        # commit AFTER side effect succeeds
    await submit(model)       # fire-and-forget — safe to lose

# Mode 3 — librdkafka background auto-commit (legacy escape hatch):
# KAFKA_CONSUMER_OVERRIDES='{"enable.auto.commit": "true"}'
router = EventRouter(channel, auto_commit=False)
```

### Error notification

```python
import logging

async def log_bad_message(raw: KafkaMessage) -> None:
    logging.error("Undispatchable: offset=%d payload=%.200r", raw.offset, raw.payload)

router = EventRouter(channel, on_error=log_bad_message)
```

---

## RecoveryReader — one-time topic replay

```python
from tradingcz.sdk.messaging import RecoveryReader

reader = RecoveryReader(events_channel, idle_timeout=2.0)

# Replays from beginning, stops after 2s of silence:
async for msg_type, model, raw in reader.replay({
    str(EventType.DATA_REQUEST): DataRequest,
    str(EventType.SERVICE_LIFECYCLE): LifecycleEvent,
}):
    reconstruct_state(model)
```

> Uses a **unique consumer group** (UUID suffix) per recovery — always starts from `earliest`.

---

## HealthPublisher — service heartbeats

```python
from tradingcz.sdk.messaging import HealthPublisher
from tradingcz.sdk.messaging import FireAndForget

faf = FireAndForget(channel, service_id="my-service")
health = HealthPublisher(faf, service_id="my-service", interval=300)

await health.start()   # emits UP, heartbeat every 300s
# ... service runs ...
await health.close()   # emits DOWN
```
