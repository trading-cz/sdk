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
| `HealthPublisher` | Emit periodic `UP` / `HEARTBEAT` / `DOWN` events | `await health.start()` / `await health.close()` |

> **TypedProducer, TypedConsumer** are Layer 2 — see [typed/_README.md](../typed/_README.md).

## When to use each

| You want to… | Use |
|-------------|-----|
| Consume messages and dispatch to handlers by type | `EventRouter` |
| Send a request and await a response (correlated by `event_id`) | `RequestReply` |
| Fire off a message and forget about it | `FireAndForget` |
| Rebuild in-memory state from the event log on startup | `ReplayConsumer` |
| Let the platform know your service is alive | `HealthPublisher` |

## Common patterns

### Consume + respond (ingestion, executor, risk)

```python
from tradingcz.sdk.messaging import EventRouter

router = EventRouter(topic, settings, group_suffix="worker")

@router.on(EventType.DATA_REQUEST, DataRequest, spawn_task=True)
async def on_request(model: DataRequest, raw: KafkaMessage) -> None:
    result = await fetch_data(model)
    await svc.publish_event(result, message_type=EventType.DATA_READY, event_id=model.event_id)

await router.start()
await svc.wait_for_shutdown()
await router.close()
```

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

# 1. Publish sentinel
await svc.publish_event(
    LifecycleEvent(service_id=svc.service_id, event=LifecycleEventType.INITIALIZING),
    message_type=EventType.SERVICE_LIFECYCLE,
)

# 2. Replay until sentinel
consumer = ReplayConsumer(topic, settings)
async for msg_type, model, raw in consumer.replay(
    types={str(EventType.DATA_REQUEST): DataRequest, …},
    until=lambda mt, m: mt == str(EventType.SERVICE_LIFECYCLE) and m.event == "initializing",
):
    reconstruct_state(msg_type, model, raw.headers)

# 3. Publish READY, start live EventRouter
await svc.publish_event(
    LifecycleEvent(service_id=svc.service_id, event=LifecycleEventType.READY),
    message_type=EventType.SERVICE_LIFECYCLE,
)
```
