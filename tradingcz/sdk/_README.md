# Application Layer — ServiceApp

Top-level convenience entry point.  Every service in the platform uses
``ServiceApp`` — it wires together Layer 3 classes so application code
doesn't have to.

``ServiceApp`` is **not a real layer** — it adds no new protocols or
messaging logic.  It's a concentrator: it creates and connects
``FireAndForget``, ``HealthPublisher``, ``RequestReply``, and optional
market-data / account clients.

## Architecture position

```
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
|-----------|-----|
| Event publishing | ``await svc.publish_event(model, message_type=…, event_id=…)`` |
| Kafka settings | ``svc.kafka_settings`` — use with EventRouter / TypedConsumer |
| Resolved topic names | ``svc.events_topic``, ``svc.topics`` |
| Health / heartbeat | Automatic ``INITIALIZING`` → ``READY`` → ``HEARTBEAT`` → ``DOWN`` |
| Graceful shutdown | ``await svc.run_until_shutdown(tasks)`` or ``await svc.wait_for_shutdown()`` |
| Market data (opt-in) | ``svc.stock.bars(…)``, ``svc.stock.stream_quotes(…)`` |
| Account (opt-in) | ``svc.positions.get_positions()``, ``svc.balance.get_balance()`` |
| Multi-broker | ``ibkr = svc.with_broker("ibkr")`` → ``ibkr.stock.bars(…)`` |

## Two usage profiles

### Minimal — transport + health only

Used by **ingestion, executor, risk**.  No feature flags needed.

```python
from tradingcz.sdk import ServiceApp

async with ServiceApp(service_id="my-service", env="dev") as svc:
    # ── Publish events ──────────────────────────────────────────────
    await svc.publish_event(
        model, message_type=EventType.DATA_READY, event_id="evt-001",
    )

    # ── Build your own consumer (EventRouter or TypedConsumer) ──────
    router = EventRouter(svc.events_topic, svc.kafka_settings, group_suffix="worker")
    # ... register handlers ...
    await router.start()

    # ── Run until SIGTERM/SIGINT ────────────────────────────────────
    await svc.run_until_shutdown(router_task)
```

### Full — market data + account + signals

Used by **simple-strategy** (ATR3, PCB Breakout).  Opt-in via feature flags.

```python
async with ServiceApp(
    service_id="my-strategy", env="dev",
    enable_stock=True,
    enable_signals=True,
) as app:
    # Historical data
    bars = await app.stock.bars(["AAPL"], days=30)

    # Streaming
    async with app.stock.stream_quotes(["AAPL"]) as stream:
        async for quote in stream:
            ...

    # Publish a signal
    await app.signals.publish(signal, event_id="evt-001")

    # Multi-broker
    ibkr = app.with_broker("ibkr")
    ibkr_bars = await ibkr.stock.bars(["AAPL"])
```

## Lifecycle

```
ServiceApp.__aenter__()
  └─ start()
       ├─ KafkaTopicRegistry (resolved topic names)
       ├─ KafkaTopicAdmin.ensure_from_config()
       ├─ TransportProducer
       ├─ FireAndForget
       ├─ HealthPublisher.initializing()  →  emits INITIALIZING
       ├─ RequestReply + BaseDataClient  (if any feature flag is on)
       │    └─ Market data clients: stock, options, corporate_actions
       │    └─ Account clients: positions, balance, orders
       ├─ _on_after_initializing()        ←  subclass hook (recovery, etc.)
       └─ HealthPublisher.ready()         →  emits READY, starts heartbeat

... application runs (heartbeat every 5 min) ...

ServiceApp.__aexit__()
  └─ close()
       ├─ HealthPublisher.down()  →  emits DOWN, stops heartbeat
       ├─ RequestReply.close()  →  cancel listener, reject pending
       └─ TransportProducer.flush()
```

## Feature flags

All default ``False`` — opt in to what you need:

| Flag | Property | What you get |
|------|----------|-------------|
| ``enable_stock`` | ``app.stock`` | Bars, quotes, trades, streaming |
| ``enable_options`` | ``app.options`` | Option snapshots |
| ``enable_corporate`` | ``app.corporate_actions`` | Dividends, splits |
| ``enable_signals`` | ``app.signals`` | Publish trading signals |
| ``enable_positions`` | ``app.positions`` | Query open positions |
| ``enable_balance`` | ``app.balance`` | Query account balance |
| ``enable_orders`` | ``app.orders`` | Submit / query orders |

**Lazy initialization**: Clients are created on first access, not at ``start()``.
A strategy that only calls ``app.stock.bars()`` never creates options, positions,
balance, or order clients.

## BrokerScope

``app.with_broker("ibkr")`` returns a ``BrokerScope`` with its own
``stock``, ``options``, and ``corporate_actions`` clients scoped to that broker.

```python
ibkr = app.with_broker("ibkr")
ibkr_bars = await ibkr.stock.bars(["AAPL"])
alpaca_bars = await app.stock.bars(["AAPL"])  # default broker
```

## Constructor reference

```
ServiceApp(
    *,
    service_id: str,               # Unique instance identifier
    env: str,                      # dev / prd — scopes topic names
    health_interval: float = 300,  # Seconds between heartbeats
    kafka_settings: KafkaSettings | None = None,  # Pre-configured (reads KAFKA_* env)
    broker: str = "alpaca",        # Default data broker
    enable_stock: bool = False,
    enable_options: bool = False,
    enable_corporate: bool = False,
    enable_signals: bool = False,
    enable_positions: bool = False,
    enable_balance: bool = False,
    enable_orders: bool = False,
)
```

