# Application Layer — ServiceApp

Top-level SDK entry point. Every service in the platform uses ``ServiceApp``.

## Minimal usage — Kafka transport + health only

Used by ingestion, executor, risk.  No feature flags needed.

```python
from tradingcz.sdk import ServiceApp
from tradingcz.sdk.models.enums.event import EventType

async with ServiceApp(service_id="my-service", env="dev") as svc:
    # ── Provided by ServiceApp ──────────────────────────────────────
    # svc.events_topic       — resolved event topic name (str)
    # svc.kafka_settings     — KafkaSettings (use with TypedConsumer/EventRouter)
    # svc.topics             — KafkaTopicRegistry (resolved topic names)
    # svc.source_app         — service_id (used in Kafka headers)

    # ── Fire-and-forget publish ─────────────────────────────────────
    await svc.publish_event(
        lifecycle_model,
        message_type=EventType.SERVICE_LIFECYCLE,
        event_id="evt-001",
    )

    # ── TypedConsumer (topic + settings, not a channel object) ──────
    from tradingcz.sdk.typed import TypedConsumer

    consumer = TypedConsumer(
        topic=svc.events_topic,
        settings=svc.kafka_settings,
        types={EventType.DATA_REQUEST: DataRequest},
        group_suffix="my-consumer",
    )

    # ── Run until SIGTERM/SIGINT, then cancel tasks ─────────────────
    await svc.run_until_shutdown(router_task, background_task)

    # ── Or wait for shutdown manually ───────────────────────────────
    await svc.wait_for_shutdown()
```

**Lifecycle**: `start()` → init topics, events producer, health. `close()` → stop health (emits DOWN), close RR + producer.

**Health**: Automatically emits `UP` on start, `HEARTBEAT` every `health_interval` seconds, `DOWN` on close.

## Strategy usage — market data + account + signals

Opt-in via feature flags.  Used by simple-strategy (ATR3, PCB Breakout).

```python
from tradingcz.sdk import ServiceApp

async with ServiceApp(
    service_id="my-strategy",
    env="dev",
    enable_stock=True,
    enable_signals=True,
) as app:
    # ── Historical data ─────────────────────────────────────────────
    bars = await app.stock.bars(["AAPL", "MSFT"], days=30)
    quotes = await app.stock.snapshots(["AAPL"])

    # ── Streaming (context manager = guaranteed unsubscribe) ────────
    async with app.stock.stream_quotes(["AAPL"]) as stream:
        async for quote in stream:
            if quote.bid_price > threshold:
                break

    # ── Account state ───────────────────────────────────────────────
    positions = await app.positions.get_positions()
    balance = await app.balance.get_balance()

    # ── Orders ──────────────────────────────────────────────────────
    order = await app.orders.submit_order(...)

    # ── Publish a trading signal ────────────────────────────────────
    await app.signals.publish(signal, event_id="abc-123")

    # ── Multi-broker ────────────────────────────────────────────────
    ibkr = app.with_broker("ibkr")
    ibkr_bars = await ibkr.stock.bars(["AAPL"], days=30)
```

**Feature flags** (all default ``False`` — opt-in):
- ``enable_stock`` → ``app.stock`` — bars, quotes, trades, streaming
- ``enable_options`` → ``app.options`` — option snapshots
- ``enable_corporate`` → ``app.corporate_actions`` — dividends, splits
- ``enable_signals`` → ``app.signals`` — fire-and-forget signal publishing
- ``enable_positions`` → ``app.positions`` — query open positions
- ``enable_balance`` → ``app.balance`` — query account balance
- ``enable_orders`` → ``app.orders`` — query order status

**Lazy initialization**: Clients are created on first access, not at ``start()``.
A strategy that only does ``app.stock.bars()`` never creates options, positions,
balance, or order clients.

**Multi-broker**: ``app.with_broker("ibkr")`` returns a ``BrokerScope`` with its
own ``stock``, ``options``, and ``corporate_actions`` clients scoped to that broker.

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

