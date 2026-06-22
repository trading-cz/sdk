# Application Layer — ServiceApp

Top-level convenience entry point.  Every service in the platform uses
``ServiceApp`` — it wires together Layer 3 classes so application code
doesn't have to.

``ServiceApp`` is **not a real layer** — it adds no new protocols or
messaging logic.  It's a concentrator: it creates and connects
``FireAndForget``, ``HealthPublisher``, ``RequestReply``, and optional
market-data / account clients.

## Architecture position

```text
┌─────────────────────────────────────────┐
│  ServiceApp  (+ BrokerScope)            │  ← Layer 4: THIS FILE
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
| Event publishing | ``await svc.publish_event(model, message_type=…, event_id=…)`` |
| Kafka settings | ``svc.kafka_settings`` — use with EventRouter / TypedConsumer |
| Resolved topic names | ``svc.events_topic``, ``svc.topics`` |
| Health / heartbeat | Automatic ``INITIALIZING`` → ``READY`` → ``HEARTBEAT`` → ``DOWN`` |
| Graceful shutdown | ``await svc.run_until_shutdown(tasks)`` or ``await svc.wait_for_shutdown()`` |
| Market data | ``svc.stock.bars(…)``, ``svc.stock.stream_quotes(…)``, ``svc.options.snapshots(…)`` |
| Signals | ``svc.signals.publish(signal, event_id=…)`` |
| Multi-broker | ``ibkr = svc.with_broker("ibkr")`` → ``ibkr.stock.bars(…)`` |

## Usage

All clients are created lazily on first access — no feature flags needed.
``RequestReply`` + ``BaseDataClient`` are always started (one consumer group
overhead is negligible at platform scale).

```python
from tradingcz.sdk import ServiceApp
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

async with ServiceApp(
    service_id="my-app",
    env="dev",
    kafka_settings=KafkaSettings(consumer_group="my-app"),
) as svc:
    # ── Publish events (fire-and-forget) ──────────────────────
    await svc.publish_event(
        model,
        message_type=EventType.SERVICE_LIFECYCLE,
        event_id="evt-001",
    )

    # ── Market data (lazy — created on first access) ──────────
    bars = await svc.stock.bars(["AAPL"], days=30)

    # ── Signals (fire-and-forget) ─────────────────────────────
    await svc.signals.publish(signal, event_id="evt-1")

    # ── Multi-broker ──────────────────────────────────────────
    ibkr = svc.with_broker("ibkr")
    ibkr_bars = await ibkr.stock.bars(["AAPL"], days=30)

    # ── Build your own consumer (EventRouter or TypedConsumer) ─
    router = EventRouter(
        svc.events_topic, svc.kafka_settings, group_suffix="worker",
    )
    # ... register handlers, start, etc. ...

    # ── Run until SIGTERM/SIGINT ──────────────────────────────
    await svc.run_until_shutdown(router_task)
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
       ├─ RequestReply + BaseDataClient    (always started)
       │    └─ Lazy clients: stock, options, corporate_actions, signals
       └─ HealthPublisher.ready()          →  emits READY, starts heartbeat

... application runs (heartbeat every 5 min) ...

ServiceApp.__aexit__()
  └─ close()
       ├─ HealthPublisher.down()  →  emits DOWN, stops heartbeat
       ├─ RequestReply.close()    →  cancel listener, reject pending
       └─ TransportProducer.close()
```

## BrokerScope

``app.with_broker("ibkr")`` returns a ``BrokerScope`` with its own
``stock``, ``options``, and ``corporate_actions`` clients scoped to that broker.

```python
ibkr = app.with_broker("ibkr")
ibkr_bars = await ibkr.stock.bars(["AAPL"])
alpaca_bars = await app.stock.bars(["AAPL"])  # default broker
```text

## Constructor reference

```python
ServiceApp(
    *,
    service_id: str,                     # Unique instance identifier
    env: str,                            # dev / prd — scopes topic names
    kafka_settings: KafkaSettings,       # Pre-configured Kafka settings (required)
    health_interval: float = 300,        # Seconds between heartbeats
    broker: str = "alpaca",              # Default data broker
)
```

## Logging

``ServiceApp`` uses the standard ``logging`` module with a module-level
logger (``logger = logging.getLogger(__name__)``).  Key lifecycle events
are logged at ``INFO`` level:

| Event | Log message |
| ------ | ------------ |
| RequestReply + BaseDataClient ready | ``ServiceApp: RequestReply + BaseDataClient ready`` |
| Start complete | ``ServiceApp started: id=%s env=%s`` |
| Shutdown requested | ``Shutdown requested — cancelling %d task(s)`` |
| Close complete | ``ServiceApp closed: id=%s`` |

Set the logger level to ``DEBUG`` for per-request tracing from
``BaseDataClient`` and ``RequestReply``.

## Exceptions

``ServiceApp`` raises ``RuntimeError`` for lifecycle violations:

| Condition | Raised by |
| ----------- | ---------- |
| Accessing data client before ``start()`` | ``stock``, ``options``, ``corporate_actions`` |
| Calling ``publish_event()`` before ``start()`` | ``publish_event()`` |
| Calling ``with_broker()`` before ``start()`` | ``with_broker()`` |

Underlying component errors (Kafka, health, RequestReply, typing)
propagate naturally — ``ServiceApp`` adds no extra error wrapping.

