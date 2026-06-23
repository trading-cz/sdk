# Application Layer — ServiceApp

Minimal Kafka transport + health + shutdown wiring shared by every
service in the platform.  ``ServiceApp`` provides ONLY the universal
boilerplate.  Apps compose their own market‑data, messaging, and domain
clients on top — no forced lazy-loading, no monolithic wiring.

## Architecture position

```text
┌─────────────────────────────────────────┐
│  YOUR APP  (ServiceApp + composition)   │  ← Layer 4: THIS FILE
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: Transport
└─────────────────────────────────────────┘
```

## What this layer provides

``ServiceApp`` gives you these **without writing any Kafka code**:

| Capability | How |
| ----------- | ----- |
| Event publishing | ``await app.publish_event(model, message_type=…, event_id=…)`` |
| Fire-and-forget transport | ``app.faf`` — compose ``SignalPublisher(faf=app.faf)`` etc. |
| Kafka settings | ``app.kafka_settings`` — use with EventRouter / TypedConsumer |
| Resolved topic names | ``app.events_topic``, ``app.topics`` |
| Health / heartbeat | Automatic ``INITIALIZING`` → ``READY`` → ``HEARTBEAT`` → ``DOWN`` |
| Graceful shutdown | ``await app.run_until_shutdown(tasks)`` or ``await app.wait_for_shutdown()`` |

## Usage

Compose your own clients on top of ``ServiceApp`` — no lazy loading,
no feature flags, no lifecycle surprises:

```python
from tradingcz.sdk import ServiceApp
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.market_data.stock_historic import StockDataClient
from tradingcz.sdk.market_data.stock_stream import StockStreamClient
from tradingcz.sdk.account.signals import SignalPublisher
from tradingcz.sdk.typed.typed_producer import TypedProducer

async with ServiceApp(
    service_id="my-app",
    env="dev",
    kafka_settings=KafkaSettings(consumer_group="my-app"),
) as app:
    # ── Compose what you need ────────────────────────────────
    rr = RequestReply(
        producer=TypedProducer(app.events_producer, app.events_topic),
        topic=app.events_topic,
        settings=app.kafka_settings,
        service_id=app.service_id,
        group_suffix="svc-reply",
    )
    await rr.start()

    transport = _DataTransport(
        rr=rr,
        producer=app.events_producer,
        settings=app.kafka_settings,
        topics=app.topics,
        service_id=app.service_id,
    )
    stock = StockDataClient(_transport=transport)
    stock_stream = StockStreamClient(_transport=transport)

    signals = SignalPublisher(faf=app.faf)

    # ── Use your clients ─────────────────────────────────────
    bars = await stock.bars(["AAPL"], days=30)
    await signals.publish(signal, event_id="evt-1")

    # ── Build your own consumer (EventRouter or TypedConsumer) ─
    router = EventRouter(
        app.events_topic, app.kafka_settings, group_suffix="worker",
    )
    # ... register handlers, start, etc. ...

    # ── Run until SIGTERM/SIGINT ─────────────────────────────
    await app.run_until_shutdown(router_task)
```

## Lifecycle

```text
ServiceApp.__aenter__()
  └─ start()
       ├─ KafkaTopicRegistry (resolved topic names)
       ├─ KafkaTopicAdmin.ensure_from_config()
       ├─ TransportProducer
       ├─ FireAndForget
       ├─ HealthPublisher.initializing()   →  emits INITIALIZING
       └─ HealthPublisher.ready()          →  emits READY, starts heartbeat

... application runs (heartbeat every 5 min) ...

ServiceApp.__aexit__()
  └─ close()
       ├─ HealthPublisher.down()  →  emits DOWN, stops heartbeat
       └─ TransportProducer.close()
```

## Constructor reference

```python
ServiceApp(
    *,
    service_id: str,                     # Unique instance identifier
    env: str,                            # dev / prd — scopes topic names
    kafka_settings: KafkaSettings,       # Pre-configured Kafka settings (required)
    health_interval: float = 300,        # Seconds between heartbeats
)
```

## Logging

``ServiceApp`` uses the standard ``logging`` module with a module-level
logger (``logger = logging.getLogger(__name__)``).  Key lifecycle events
are logged at ``INFO`` level:

| Event | Log message |
| ------ | ------------ |
| Start complete | ``ServiceApp started: id=%s env=%s`` |
| Shutdown requested | ``Shutdown requested — cancelling %d task(s)`` |
| Close complete | ``ServiceApp closed: id=%s`` |

## Exceptions

``ServiceApp`` propagates errors from underlying components (Kafka,
health) naturally — it adds no extra error wrapping.  There are no
lazy-loading lifecycle violations (no pre-start guard checks).

## What changed from the old ServiceApp

The old ``ServiceApp`` auto-wired ``RequestReply``, market-data clients,
``SignalPublisher``, and ``BrokerScope``.  The new ``ServiceApp`` is
**minimal** — only transport, health, and shutdown.  Compose what you
need explicitly:

| Old (monolithic) | New (compose) |
|---|---|
| ``app.stock`` | ``StockDataClient(_transport=transport)`` |
| ``app.stock_stream`` | ``StockStreamClient(_transport=transport)`` |
| ``app.options`` | ``OptionsHistoricDataClient(_transport=transport)`` |
| ``app.signals`` | ``SignalPublisher(faf=app.faf)`` |
| ``app.with_broker()`` | Create a second transport with different broker |
| ``app.publish_event()`` | ``app.publish_event()`` (unchanged) |
| ``app.kafka_settings`` | ``app.kafka_settings`` (unchanged) |
| ``app.events_topic`` | ``app.events_topic`` (unchanged) |

