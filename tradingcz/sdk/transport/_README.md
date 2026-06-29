# transport — Layer 1: Kafka Wire Protocol

Direct Kafka communication primitives. Bytes in, bytes out. No typing, no serialization — just raw Kafka with headers.

## Architecture position

```text
┌─────────────────────────────────────────┐
│  Your App (direct wiring)               │  ← Layer 4: Application
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: THIS PACKAGE
└─────────────────────────────────────────┘
```

## TransportConsumer

Async consumer — poll batches, iterate messages, commit offsets, handle corrupt messages.

```python
from tradingcz.sdk.transport import TransportConsumer, KafkaSettings, KafkaMessage

settings = KafkaSettings(consumer_group="my-service")
consumer = TransportConsumer("dev-event", settings, group_suffix="worker-1")

# Option 1: poll() — pull batches (caller controls lifecycle)
try:
    while True:
        batch: list[KafkaMessage] = await consumer.poll()
        for msg in batch:
            event_type = msg.headers.get("event_type")
            print(f"offset={msg.offset} type={event_type}")
            await consumer.commit(msg)  # commit after processing
finally:
    await consumer.close()

# Option 2: async iterator — convenience, auto-close on exit
async for msg in consumer:
    print(f"offset={msg.offset} payload={msg.payload!r}")
    await consumer.commit(msg)
# consumer is closed automatically when iteration ends

# On corrupt messages — optional error callback
async def on_error(partition: int, offset: int, error: str) -> None:
    print(f"Corrupt message at p={partition} o={offset}: {error}")

consumer = TransportConsumer("dev-event", settings, "w1", on_error=on_error)
async for msg in consumer:
    # corrupt messages are auto-skipped (offset committed +1)
    await consumer.commit(msg)
```

**Key points:**
- One `TransportConsumer` = one `AIOConsumer` = one consumer group
- `group_suffix` controls isolation: same suffix = competing consumers, unique suffix = independent replay
- Corrupt messages are automatically skipped (offset committed past the corrupt record)
- `commit(msg)` commits offset + 1 for the message's topic/partition

## TransportProducer

Async producer — send raw bytes, flush, track delivery errors.

```python
from tradingcz.sdk.transport import TransportProducer, KafkaSettings

settings = KafkaSettings(consumer_group="my-service")
producer = TransportProducer(settings)

# Send raw bytes
await producer.send(
    "dev-event",
    b'{"symbols":["AAPL"]}',
    key="my-key",
    headers={"event_type": "data.request", "source_app": "my-service"},
)

# Guarantee delivery — flush blocks until all queued messages are sent
await producer.flush(timeout=30.0)

# Close when done — flushes pending messages and releases the producer
await producer.close()

# On delivery failure — optional synchronous error callback
def on_error(topic: str, partition: int, offset: int, error_str: str) -> None:
    print(f"Delivery failed for {topic} [{partition}] offset={offset}: {error_str}")

producer = TransportProducer(settings, on_error=on_error)
```

**Key points:**
- Wraps `confluent_kafka.Producer` (sync) with `run_in_executor` for async
- `flush()` blocks until all messages are delivered or timeout
- `close()` flushes pending messages then releases the producer; use-after-close raises `RuntimeError`
- Delivery errors are reported synchronously via the ``on_error`` callback (runs on librdkafka thread)
- One `TransportProducer` per process (shared across all channels)

## KafkaTopicAdmin

Creates Kafka topics via Admin API. Instance-based, reuses a single AdminClient connection, caches created topics to avoid redundant API calls.

```python
from tradingcz.sdk.transport import KafkaTopicAdmin, KafkaTopicConfig, KafkaSettings

settings = KafkaSettings(consumer_group="my-service")

async with KafkaTopicAdmin(settings) as admin:
    # Create a topic with custom config
    await admin.ensure(
        "dev-stock-market-stream-data",
        num_partitions=5,
        replication_factor=2,
        retention_ms=259_200_000,  # 3 days
        cleanup_policy="delete",
    )

    # Create from a KafkaTopicConfig
    config = KafkaTopicConfig(name="dev-event", partitions=1)
    await admin.ensure_from_config(config)
# auto-closed on exit
```

**Key points:**
- Lazy `AdminClient` — created on first `ensure()` call, reused thereafter
- Instance-level cache — `_created` set prevents duplicate Admin API calls within the same instance
- Thread-safe for async usage (confluent-kafka AdminClient is thread-safe)
- `async with` ensures `close()` is called even if topic creation fails; use-after-close raises `RuntimeError`
