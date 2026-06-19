# typed — Layer 2: Typed Wrappers

Typed send/receive on top of `KafkaChannel`.  Adds Pydantic model serialization
and header-based dispatch.  Sits between the raw transport (Layer 1) and
messaging patterns (Layer 3).

## Architecture position

```
┌─────────────────────────────────────────┐
│  ServiceApp / TradingApp                │  ← Layer 4: Application
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: THIS PACKAGE
├─────────────────────────────────────────┤
│  KafkaChannel / KafkaTransport          │  ← Layer 1: Kafka layer
└─────────────────────────────────────────┘
```

## Components

| Class | Sends? | Receives? |
|-------|--------|-----------|
| `TypedProducer` | ✅ typed models → Kafka (auto-headers) | ❌ |
| `TypedConsumer` | ❌ | ✅ header-based dispatch → typed models |

## TypedProducer

Publish Pydantic models with auto-built headers.  No factories, no callbacks —
just ``send(value)`` and ``flush()``.

```python
from tradingcz.sdk.typed import TypedProducer
from tradingcz.sdk.models.market import Bar

producer = TypedProducer(channel, source_app="ingestion", broker="alpaca")

# Headers auto-built from model class name + attributes:
await producer.send(Bar(symbol="AAPL", ...))
await producer.flush()  # guarantee delivery

# Or use as context manager for auto-flush:
async with TypedProducer(channel, source_app="ingestion") as p:
    await p.send(Bar(symbol="MSFT", ...))
```

Headers are built by :meth:`DataHeader.for_item` in ``transport/headers.py``.
For custom header logic, subclass ``TypedProducer`` and override ``send()``.

## TypedConsumer

Header-based typed dispatch from a shared multi-type Kafka topic.
Iterate directly — no `.parse()`, `.consume()`, or `.consume_with_metadata()`.
One yield shape: ``(msg_type, model, raw)``.

```python
from tradingcz.sdk.typed import TypedConsumer
from tradingcz.sdk.models.enums.event import EventType

consumer = TypedConsumer(
    channel,
    types={
        EventType.DATA_REQUEST: DataRequest,
        EventType.SERVICE_LIFECYCLE: LifecycleEvent,
    },
    # auto_commit=True by default — commits after each parsed message
    # on_error=my_handler,         # optional undispatchable callback
)

async for msg_type, model, raw in consumer:
    if msg_type == EventType.DATA_REQUEST:
        await handle_request(model)
    elif msg_type == EventType.SERVICE_LIFECYCLE:
        await handle_lifecycle(model)
```

### TypedConsumer vs TypedProducer

| | TypedProducer | TypedConsumer |
|---|---|---|
| Direction | → Kafka | ← Kafka |
| Generic? | No | No |
| Constructor | `channel, source_app=, broker=` | `channel, types=dict` |
| Interface | `send(value)`, `flush()`, `async with` | `async for msg_type, model, raw in consumer` |
| Headers | Auto-built via `DataHeader.for_item()` | Read via `Header.EVENT_TYPE` |
| Layer 3 users | FireAndForget | EventRouter, RecoveryReader |
