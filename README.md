# trading-sdk

Shared SDK for the trading-cz platform — typed Kafka messaging, market data clients, and strategy tooling.

Requires **Python ≥ 3.14**.

## Structure

```
tradingcz/sdk/
│
├── account/             # Balance, Orders, Positions clients
├── health/              # HealthMonitor
├── indicators/          # Technical indicators
├── lang/                # Lazy, Registry, Retry, shutdown handlers
├── market_data/         # Stock, Options, Corporate Actions clients
├── messaging/           # Layer 3 — EventRouter, RequestReply, F&F, RecoveryReader
├── models/              # Pydantic models, enums, events
├── serialization/       # JsonCodec, JsonSerializer
├── transport/           # Layer 1 — KafkaChannel, KafkaTransport, KafkaSettings
├── typed/               # Layer 2 — TypedProducer, TypedConsumer
│
├── _README.md           # Layer 4 — ServiceApp & TradingApp
├── exceptions.py        # SdkError hierarchy
├── logging.py           # setup_logging(), LokiJSONFormatter
├── service_app.py       # ServiceApp — base for ALL services
└── trading_app.py       # TradingApp — batteries-included strategy entry
```

## Layered Architecture

Each layer depends only on the layer below it. A layer never reaches up.

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 4 — Application                                            │
│   ServiceApp, TradingApp                                         │
│   Owns: service lifecycle, shutdown, app-level wiring            │
├──────────────────────────────────────────────────────────────────┤
│ Layer 3 — Messaging Patterns                                     │
│   EventRouter, RequestReply, FireAndForget, RecoveryReader       │
│   Owns: handler dispatch, request/reply correlation, idle policy │
├──────────────────────────────────────────────────────────────────┤
│ Layer 2 — Typed Wrappers                                         │
│   TypedProducer, TypedConsumer                                   │
│   Owns: serialization, header-based dispatch, on_error routing   │
├──────────────────────────────────────────────────────────────────┤
│ Layer 1 — Transport                                              │
│   KafkaTransport, KafkaChannel, ReceiveSession, KafkaMessage     │
│   Owns: bytes ↔ Kafka, consumer lifecycle, offset commit         │
└──────────────────────────────────────────────────────────────────┘
```

### Layer responsibilities

| Layer | Must handle | Must NEVER |
|-------|-------------|------------|
| **L1 Transport** | Raw Kafka I/O, consumer groups, offsets, corrupt-message commit | Serialize/deserialize payloads, inspect headers, decide business policy |
| **L2 Typed** | Model serialization, `event_type` dispatch, route errors to `on_error` | Commit offsets directly (delegates to L1), know about handlers |
| **L3 Messaging** | Handler registration, request/reply correlation, idle-timeout policy, auto vs manual commit | Decode raw bytes, manage consumer lifecycle directly |
| **L4 Application** | Service lifecycle, topic wiring, health publishing | Touch Kafka internals |

### Data flow (receive path)

```
Kafka broker
  │
  ▼
ReceiveSession.poll()          ← L1: consume() batch → list[KafkaMessage]
  │  (corrupt msg? → log + commit offset + skip — no recoverable data)
  ▼
TypedConsumer.__aiter__        ← L2: dispatch by event_type header → (type, model, raw)
  │  (bad JSON / unknown type? → on_error(msg) + skip)
  ▼
EventRouter.run()              ← L3: match msg_type → registered handler
  │  (handler raises? → log, don't commit → at-least-once)
  ▼
Application handler            ← L4: business logic
```

### Cross-cutting rules

**`on_error`** — same name at every layer, type matches what the layer naturally has:

| Layer | Signature | Called with |
|-------|-----------|-------------|
| L1 `ReceiveSession` | `(partition: int, offset: int, error: str)` | Corrupt Kafka message — no payload/headers available |
| L2 `TypedConsumer` | `(msg: KafkaMessage)` | Dispatch failure — message metadata intact |
| L3 `EventRouter` | `(msg: KafkaMessage)` | Passed through to `TypedConsumer` |

Each layer's `on_error` is independent. L2 does not pass its callback to L1 — they handle different error categories.

**Offset commit** — ownership is explicit:

| Who creates the session | Who commits |
|---|---|
| `TypedConsumer` | `TypedConsumer` (auto_commit flag) |
| `EventRouter` | `EventRouter` (`_dispatch` method, after handler success) |
| `RequestReply._listen()` | `RequestReply` (every message, match or skip) |
| `RecoveryReader` | Nobody (ephemeral group, discarded after replay) |

**Exceptions** — propagate, don't swallow:

| Error | Layer | Action |
|-------|-------|--------|
| Corrupt Kafka message (`msg.error()`) | L1 | Log, commit offset, skip — no recoverable data |
| Bad JSON / missing header / unknown type | L2 | Call `on_error(msg)`, skip |
| Handler exception | L3 | Log, **don't** commit → re-delivered on restart |
| Broker down / connection lost | L1 | Exception propagates ↑ — fail fast |

**`ReceiveSession`** is single-use — one consumer per session. Call `poll()` for pull-based control or `async for` for convenience. Consumer is created in `__init__`, subscribed lazily, closed via `finally` or explicit `close()`.

**Batch polling** — `poll()` uses `consume()` under the hood for throughput. Up to `consumer_batch_size` messages per `consumer_poll_timeout_ms` window. Returns `list[KafkaMessage]` (empty = no messages in window).
