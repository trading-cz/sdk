# Application Layer — Direct Wiring

Every service owns its Kafka transport, health, and messaging setup
directly — no base class, no inheritance, no magic.  Compose the SDK
building blocks you need explicitly.

This is the pattern used by **ingestion**, **risk**, **executor**,
and **simple-strategy**.

## Architecture position

```text
┌─────────────────────────────────────────┐
│  YOUR APP  (direct composition)         │  ← Layer 4: THIS FILE
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: Transport
└─────────────────────────────────────────┘
```

## Pattern

Each service creates its own transport primitives directly:

| Capability | How |
| ----------- | ----- |
| Kafka producer | ``TransportProducer(kafka_settings)`` |
| Resolved topic names | ``KafkaTopicRegistry(env=env)`` |
| Topic admin | ``KafkaTopicAdmin(kafka_settings)`` |
| Fire-and-forget | ``FireAndForget(TypedProducer(producer, topic), service_id)`` |
| Health / heartbeat | ``HealthPublisher(faf, service_id, interval=300)`` |
| Graceful shutdown | ``setup_shutdown_handlers(shutdown_event)`` |

## Usage

```python
import asyncio
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.messaging.router import EventRouter
from tradingcz.sdk.health.publisher import HealthPublisher
from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.market_data.stock_historic import StockDataClient
from tradingcz.sdk.market_data.stock_stream import StockStreamClient
from tradingcz.sdk.account.signals import SignalPublisher
from tradingcz.sdk.typed.typed_producer import TypedProducer
from tradingcz.sdk.lang.async_utils import setup_shutdown_handlers

async def main():
    settings = KafkaSettings(consumer_group="my-app")
    service_id = "my-app"
    env = "dev"

    # ── Kafka transport ──────────────────────────────────
    topics = KafkaTopicRegistry(env=env)
    events_topic = topics.events.name
    producer = TransportProducer(settings)
    topic_admin = KafkaTopicAdmin(settings)
    faf = FireAndForget(TypedProducer(producer, events_topic), service_id)
    health = HealthPublisher(faf, service_id, interval=300.0)

    # ── Create topics, emit health ────────────────────────
    await topic_admin.ensure_from_config(topics.events)
    await health.initializing()

    # ── RequestReply + market data transport ──────────────
    rr = RequestReply(
        producer=TypedProducer(producer, events_topic),
        topic=events_topic,
        settings=settings,
        service_id=service_id,
        group_suffix="svc-reply",
    )
    await rr.start()
    transport = _DataTransport(
        rr=rr, producer=producer, settings=settings,
        topics=topics, service_id=service_id,
    )

    # ── Compose clients ───────────────────────────────────
    stock = StockDataClient(_transport=transport)
    stock_stream = StockStreamClient(_transport=transport)
    signals = SignalPublisher(faf=faf)

    await health.ready()

    # ── Consume events ────────────────────────────────────
    router = EventRouter(events_topic, settings, group_suffix="worker")
    # ... register handlers ...
    await router.start()

    # ── Shutdown ──────────────────────────────────────────
    shutdown = asyncio.Event()
    setup_shutdown_handlers(shutdown)
    await shutdown.wait()
    await health.down()
    await router.close()
    await rr.close()
    await producer.close()
    await topic_admin.close()
```

## Lifecycle

```text
app.start()
  ├─ KafkaTopicRegistry (resolved topic names)
  ├─ KafkaTopicAdmin.ensure_from_config()
  ├─ TransportProducer
  ├─ FireAndForget
  ├─ HealthPublisher.initializing()   →  emits INITIALIZING
  └─ HealthPublisher.ready()          →  emits READY, starts heartbeat

... application runs (heartbeat every 5 min) ...

app.stop()
  ├─ HealthPublisher.down()  →  emits DOWN, stops heartbeat
  └─ TransportProducer.close()
```

## Logging

Use the standard ``logging`` module with a module-level logger
(``logger = logging.getLogger(__name__)``).  Key lifecycle events
should be logged at ``INFO`` level.

## Exceptions

Each service propagates errors from underlying components (Kafka,
health) naturally — no extra error wrapping.  There are no
lazy-loading lifecycle violations (no pre-start guard checks).

