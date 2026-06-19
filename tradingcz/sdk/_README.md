# Application Layer — ServiceApp & TradingApp

Top-level SDK entry points. Every service in the platform uses one of these.

## ServiceApp — base for ALL services

Provides Kafka transport, events channel, health heartbeats, and graceful shutdown.
Used by ingestion, executor, risk.

```python
from tradingcz.sdk import ServiceApp
from tradingcz.sdk.models.enums.event import EventType

async with ServiceApp(service_id="my-service", env="dev", health_interval=300) as svc:
    # ── Provided by ServiceApp ──────────────────────────────────────
    # svc.events_channel   — KafkaChannel for the events topic
    # svc.transport        — KafkaTransport (shared producer, channel cache)
    # svc.topics           — TopicRegistry (resolved topic names)
    # svc.source_app       — service_id (used in Kafka headers)

    # ── Fire-and-forget publish ─────────────────────────────────────
    await svc.publish_event(
        lifecycle_model,
        message_type=EventType.SERVICE_LIFECYCLE,
        event_id="evt-001",
    )

    # ── Run until SIGTERM/SIGINT, then cancel tasks ─────────────────
    await svc.run_until_shutdown(router_task, background_task)

    # ── Or wait for shutdown manually ───────────────────────────────
    await svc.wait_for_shutdown()
```

**Lifecycle**: `start()` → init transport, topics, events channel, health. `close()` → stop health (emits DOWN), close transport.

**Health**: Automatically emits `UP` on start, `HEARTBEAT` every `health_interval` seconds, `DOWN` on close.

## TradingApp — strategy entry point

Extends `ServiceApp` with market data clients, account state, and signal publishing.
Used by simple-strategy (ATR3, PCB Breakout).

```python
from tradingcz.sdk import TradingApp

async with TradingApp(service_id="my-strategy", env="dev", health_interval=300) as app:
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

    # ── Disable unused clients (before start) ───────────────────────
    app.with_options(False).with_balance(False)
```

**Builder pattern**: `with_stock(False)`, `with_options(False)`, `with_signals(False)` etc.
disable client initialization — call **before** `start()`.

**Multi-broker**: `app.with_broker("ibkr")` returns a `_BrokerScope` with its own
`stock`, `options`, and `corporate_actions` clients scoped to that broker.
