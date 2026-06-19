# transport — Layer 1: Kafka Wire Protocol

Direct Kafka communication primitives. Bytes in, bytes out. No typing, no serialization — just raw Kafka with headers.

## Architecture position

```
┌─────────────────────────────────────────┐
│  ServiceApp / TradingApp                │  ← Layer 4: Application
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  KafkaChannel / ReceiveSession          │  ← Layer 1: THIS PACKAGE
└─────────────────────────────────────────┘
```

## Components

| Class | Role |
|-------|------|
| `KafkaSettings` | Env-driven config: bootstrap servers, consumer group, overrides |
| `KafkaTransport` | One per process — shared `Producer`, channel cache, topic auto-creation |
| `KafkaChannel` | One per topic — send raw bytes + headers |
| `ReceiveSession` | One per consumer — iterate messages, **commit offsets** |
| `KafkaMessage` | Pure data: `payload`, `key`, `headers`, `offset`, `partition`, `topic` |
| `Header` / `EventHeaders` / `DataHeaders` | Canonical header keys and typed header models |
| `KafkaKey` | Routing key builder for Kafka partitions |
| `DedupFilter` | In-memory sequence-number deduplication |

---

## Why `ReceiveSession`?

`KafkaMessage` is **pure data** — a frozen dataclass with no behavior. Commit is a
capability, not a property of a message. It belongs to the thing that *received*
the message: the consumer.

But there's a problem: `KafkaChannel` can have **multiple concurrent consumers**
(each `receive()` call creates a fresh `AIOConsumer` with its own group id).
If commit lived on `KafkaChannel`, which consumer would it commit to?

`ReceiveSession` solves this: one session = one `AIOConsumer` = one commit
authority. You iterate the session to get messages, and call `session.commit(msg)`
on the same session. No ambiguity, no hidden state on the message.

### Trade-off analysis

| Approach | Problem |
|----------|---------|
| `msg.commit()` (old) | `KafkaMessage` frozen dataclass mutated via `object.__setattr__`; `getattr` to discover hidden `_commit_fn`; commit capability smuggled in a data object |
| `channel.commit(msg)` | Channel can have N concurrent consumers — which one commits? |
| `session.commit(msg)` (current) | One extra object. But: explicit, typed, one authority per consumer |

The extra object is justified. The same pattern appears in Kafka's own Java
client (`ConsumerRecord` is data; `KafkaConsumer` owns `commitSync()`).

---

## KafkaMessage — pure data

```python
from tradingcz.sdk.transport import KafkaMessage

msg.payload       # bytes — raw JSON
msg.key           # str   — routing key ("" if none)
msg.headers       # dict[str, str] — decoded headers
msg.offset        # int   — Kafka offset
msg.partition     # int   — Kafka partition
msg.topic         # str   — topic name

# No commit(). No _commit_fn. No getattr. Pure data, always.
# Construct manually for tests — no RuntimeError on missing commit.
```

---

## ReceiveSession — iterate + commit

```python
from tradingcz.sdk.transport import KafkaChannel

channel = await transport.channel("dev-event")
session = channel.receive(group_suffix="my-consumer")

async for msg in session:
    # ... process msg ...
    await session.commit(msg)  # commit THIS session's offset
```

**Key property**: the session owns one `AIOConsumer`. You can only commit
messages that came from this session — and only while the session is active
(before the iterator exits).

---

## KafkaChannel — send (shared producer) + create sessions

```python
from tradingcz.sdk.transport import KafkaChannel, EventHeaders, KafkaKey
from tradingcz.sdk.models.enums.event import EventType

# SEND — shared Producer, async-safe via run_in_executor:
headers = EventHeaders(
    event_type=EventType.DATA_REQUEST,
    source_app="my-service",
    event_id="req-001",
).to_kafka()

await channel.send(
    b'{"symbols":["AAPL"]}',
    key=KafkaKey.for_event(EventType.DATA_REQUEST, "my-service", "req-001"),
    headers=headers,
)
await channel.flush()  # guarantee delivery

# CREATE SESSION — one per consumer group:
session = channel.receive(group_suffix="my-consumer")
async for msg in session:
    event_type = msg.headers.get("event_type", "")
    print(f"offset={msg.offset} type={event_type}")
    await session.commit(msg)

# Concurrent consumers — each gets its own session:
session_a = channel.receive(group_suffix="worker-a")
session_b = channel.receive(group_suffix="worker-b")
# Each has its own AIOConsumer, own consumer group, own commits.
```

> `group_suffix` controls isolation. Same suffix = shared consumer group
> (competing consumers). Unique suffix = independent replay from `earliest`.

---

## KafkaSettings

```python
from tradingcz.sdk.transport import KafkaSettings

settings = KafkaSettings(consumer_group="my-service")
# All fields env-driven (prefix KAFKA_):
#   KAFKA_BOOTSTRAP_SERVERS=localhost:9092
#   KAFKA_CONSUMER_GROUP=my-service

# Producer config:
settings.producer_config()
# → {"bootstrap.servers": "...", "linger.ms": "5", "compression.type": "snappy", ...}

# Consumer config:
settings.consumer_config(group_id="my-service-dev-event-rr")
# → {"bootstrap.servers": "...", "group.id": "my-service-dev-event-rr",
#     "auto.offset.reset": "earliest", "enable.auto.commit": "false"}
```

> **`enable.auto.commit` is `false`** — the SDK owns all offset commits.
> librdkafka background commit is disabled. Every commit is an explicit
> `session.commit(msg)` call.

---

## KafkaTransport — shared producer + channel cache

```python
from tradingcz.sdk.transport import KafkaTransport, KafkaSettings

settings = KafkaSettings(consumer_group="my-service")
transport = KafkaTransport(settings)

channel = await transport.channel("dev-event")
# → KafkaChannel with shared SyncProducer, topic auto-created if needed

same = await transport.channel("dev-event")  # cached — same instance
await transport.close()  # flush producer, close channels
```

---

## Headers

```python
from tradingcz.sdk.transport import Header, EventHeaders, DataHeaders

# Canonical keys:
Header.EVENT_TYPE   # "event_type"
Header.SOURCE_APP   # "source_app"
Header.EVENT_ID     # "event_id"
Header.SEQUENCE     # "sequence"
Header.BROKER       # "broker"
Header.SOURCE       # "source"

# Event-topic headers:
eh = EventHeaders(event_type=EventType.DATA_REQUEST, source_app="ingestion", event_id="abc-123")
wire = eh.to_kafka()                         # → dict[str, str]
parsed = EventHeaders.from_kafka(wire)       # → EventHeaders instance

# Data-topic headers (includes sequence for dedup):
dh = DataHeaders(event_type=EventType.BAR, source_app="ingestion", broker="alpaca", symbol="AAPL", sequence=42)
wire = dh.to_kafka()
```

---

## Usage patterns across layers

### Layer 1 — raw (this package)
```python
session = channel.receive(group_suffix="my-app")
async for msg in session:
    await handle(msg.payload)
    await session.commit(msg)
```

### Layer 2 — typed (TypedConsumer)
```python
consumer = TypedConsumer(channel, types={...}, auto_commit=True)
async for msg_type, model, raw in consumer:
    await handle(model)
    # auto_commit=True → committed automatically
    # auto_commit=False → call consumer.commit(raw)
```

### Layer 3 — routed (EventRouter)
```python
router = EventRouter(channel, auto_commit=False)
router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent, my_handler)
await router.run()

# In handler:
async def my_handler(model, raw):
    await db.save(model)
    await router.commit(raw)   # explicit control
```

### Layer 4 — batteries-included (ServiceApp)
```python
async with ServiceApp(service_id="my-service", env="dev") as svc:
    await svc.publish_event(model, event_type=..., event_id=...)
    await svc.run_until_shutdown(router_task)
```
