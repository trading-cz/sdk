# trading-sdk

Shared SDK for the trading-cz platform — typed Kafka messaging, market data
clients, health monitoring, and strategy tooling.  Every service in the
platform (ingestion, executor, risk, simple-strategy) is built on this SDK.

Requires **Python ≥ 3.14**.

## Install

```bash
pip install trading-sdk
```

With optional dev tooling:

```bash
pip install trading-sdk[dev]      # pytest, ruff, mypy
```

To uninstall:

```bash
pip uninstall trading-sdk
```

## What it does

| Capability | Where |
| ---------- | ----- |
| **Kafka transport** — produce/consume raw bytes, manage consumer groups, commit offsets | `transport/` |
| **Typed messaging** — serialize/deserialize Pydantic models, header-based dispatch | `typed/` |
| **Messaging patterns** — request/reply, fire-and-forget, event routing, startup replay | `messaging/` |
| **Application wiring** — one-line lifecycle (health, shutdown, topic admin) | `service_app.py` |
| **Market data clients** — bars, quotes, streaming, options, corporate actions | `market_data/`, `account/` |
| **Shared models** — enums, events, order types, indicators | `models/`, `indicators/` |

## Architecture

Four layers, each depends only on the one below it:

```text
┌─────────────────────────────────────────┐
│  ServiceApp  (+ BrokerScope)            │  ← Layer 4: Application wiring
├─────────────────────────────────────────┤
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging patterns
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer          │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  TransportProducer / TransportConsumer  │  ← Layer 1: Raw Kafka transport
└─────────────────────────────────────────┘
```

Detailed docs live in each package:

| Layer | Readme |
| ----- | ------ |
| L1 — Transport | [`transport/_README.md`](tradingcz/sdk/transport/_README.md) |
| L2 — Typed | [`typed/_README.md`](tradingcz/sdk/typed/_README.md) |
| L3 — Messaging | [`messaging/_README.md`](tradingcz/sdk/messaging/_README.md) |
| L4 — Application | [`_README.md`](tradingcz/sdk/_README.md) |

## Quick start

```python
from tradingcz.sdk import ServiceApp

async with ServiceApp(service_id="my-app", env="dev") as svc:
    # Publish events (fire-and-forget)
    await svc.publish_event(model, message_type=EventType.DATA_READY, event_id="evt-001")

    # Consume with EventRouter (L3)
    router = EventRouter(svc.events_topic, svc.kafka_settings, group_suffix="worker")
    await router.start()

    await svc.run_until_shutdown(tasks)
```

## Naming conventions

- **Layer files**: `snake_case` — `fire_and_forget.py`, `request_reply.py`
- **Class names**: `PascalCase` — `EventRouter`, `FireAndForget`, `ReplayConsumer`
- **Layer 3 classes**: `NounPhrase` describing the pattern — `EventRouter`, `RequestReply`
- **Private helpers**: `_LeadingUnderscore` — `_Registration`, `_BrokerScope`
- **`async with`** for objects with start/stop lifecycle
- **`async for`** for consumers that auto-close on loop exit

## Tests

Smoke tests live in the [`testing`](https://github.com/trading-cz/testing) repository.
Local unit tests:

```bash
pytest tests/ test_service_app_smoke.py -v
```
