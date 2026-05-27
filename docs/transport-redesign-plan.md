# Transport Layer Redesign Plan

**Date**: 2026-05-27  
**Status**: Step 1 ✅ — Step 2 ✅ — Step 3 ✅ — Step 4 ⏭️ — Step 5 ✅  
**Phase**: PoC — Migration complete (executor deferred)

---

## Design Principles

1. **Each app owns its Kafka setup** — SDK provides building blocks (Channel, TypedProducer, TypedConsumer, JsonCodec), each service composes its own pipeline
2. **SDK contains only shared, reusable code** — no domain models in transport layer
3. **Layer 0 (bytes) → Layer 1 (serialization) → Layer 2 (typed streams)**
4. **Kafka is pluggable** — no service imports `confluent_kafka` or `aiokafka` directly
5. **Keep it simple** — JSON-only serialization for 2026, `schema_version` field for future-proofing

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Layer 2: Typed Streams (Generic)                        │
│  ┌──────────────────┐  ┌──────────────────────────────┐  │
│  │ TypedProducer[T]  │  │ TypedConsumer[T]             │  │
│  │  .send(value: T)  │  │  .consume() → AsyncIter[T]   │  │
│  └────────┬─────────┘  └──────────────┬───────────────┘  │
│           │                           │                   │
├───────────┼───────────────────────────┼───────────────────┤
│  Layer 1: Serialization               │                   │
│  ┌────────┴───────────────────────────┴────────────────┐  │
│  │  Serializer[T] / Deserializer[T] / Codec[T]         │  │
│  │  JsonCodec[T] — for any Pydantic model              │  │
│  └──────────────────────┬──────────────────────────────┘  │
│                         │                                  │
├─────────────────────────┼──────────────────────────────────┤
│  Layer 0: Byte Transport│                                  │
│  ┌──────────────────────┴──────────────────────────────┐  │
│  │  Message(payload: bytes, key: str)                  │  │
│  │  Channel: .send(payload, key) / .receive()          │  │
│  │  Transport: .channel(name) → Channel                │  │
│  │  KafkaTransport (confluent-kafka)                   │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## SDK Package Layout (Target)

```
sdk/tradingcz/
├── transport/            # Layer 0: Channel, Transport, KafkaTransport (KEEP)
│   ├── protocol.py
│   └── kafka.py
├── serialization/        # Layer 1: Codec abstraction (NEW)
│   ├── protocol.py       # Serializer[T], Deserializer[T], Codec[T]
│   └── json_codec.py     # JsonCodec[T] for Pydantic models
├── typed/                # Layer 2: Typed wrappers (NEW)
│   └── stream.py         # TypedProducer[T], TypedConsumer[T]
├── topics.py             # TopicConfig, TopicRegistry (NEW — replaces lost tradingcz.kafka)
├── config/settings.py    # KafkaSettings, ServerSettings (KEEP)
├── model/                # Domain models (KEEP, decouple from transport)
│   ├── ingestion/        # Bar, Quote, Trade, Snapshot
│   ├── events.py         # DataRequest, DataReady, DataError
│   ├── signal.py         # TradingSignal
│   ├── event_bus.py      # → DEPRECATED (replaced by TypedProducer/Consumer)
│   └── ...
├── receiver/             # → DEPRECATED (replaced by TypedConsumer + per-service correlator)
└── indicators/           # ATR, SMA, etc. (KEEP)
```

## Migration Steps

### Step 1: SDK ✅ DONE
- [x] Recover `Topics`/`keys` as `tradingcz/transport/kafka/topics.py` tracked in git
- [x] Add `tradingcz/serialization/` package (protocol.py, json_codec.py)
- [x] Add `tradingcz/transport/stream.py` (TypedProducer, TypedConsumer)
- [x] Deprecate `tradingcz/receiver/` (add deprecation warnings)
- [x] Deprecate `tradingcz/model/event_bus.py`
- [x] Update `tradingcz/__init__.py` and subpackage exports
- [x] Remove orphaned `tradingcz/kafka/` dir (only .pyc files, no source)
- [x] Bump version to v0.1.0
- [ ] Tag and release

### Step 2: Ingestion ✅ DONE
- [x] Replace `EventBus` → `TypedConsumer[DataRequest]` / `TypedProducer[DataReady|DataError]`
- [x] Rename `stream_data.alpaca` → `market_data` (5 partitions, symbol-keyed)
- [x] Use `TopicRegistry` for topic names (env-agnostic, K8s-level isolation)
- [x] Remove `from tradingcz.kafka import Topics, data_key`
- [x] Update `smoke_test.py` and `test_stream_integration.py` topic references
- [x] Activate producer overrides in deployment YAML (`linger.ms=5`, `compression.type=snappy`)
- [x] Bump SDK dep to v0.1.0

### Step 3: Simple-Strategy ✅ DONE
- [x] Remove `import confluent_kafka` — use `TypedProducer[TradingSignal]` for signal emission
- [x] Replace `ConfluenceKafkaReceiverTransport` → `KafkaTransport` + `RequestCorrelator` (thin, ~80 LOC helper in `tradingcz/strategy/common/correlator.py`)
- [x] Replace `from tradingcz.kafka import Topics` → `from tradingcz.transport.kafka import TopicRegistry`
- [x] Replace `from tradingcz.kafka.keys import signal_key` → `TopicRegistry.signal_key()`
- [x] Rewrite `atr3_open_stop/app.py` — zero confluent-kafka references
- [x] Rewrite `pcb_breakout/integration.py` — zero confluent-kafka references
- [x] Remove `confluent-kafka` from `pyproject.toml` dependencies
- [x] Bump SDK dep to v0.1.0

### Step 4: Executor ⏭️ SKIPPED
- [ ] Deferred — colleague's project, needs alignment first
- [ ] Replace custom `KafkaListener` with `TypedConsumer[ExecutionRequestEvent]`
- [ ] Unify under `KafkaSettings` (`KAFKA_` prefix, drop `KAFKA_LISTENER_`)
- [ ] Bump SDK dep to v0.1.0

### Step 5: Config Repo ✅ DONE
- [x] Rename Strimzi KafkaTopic `dev-event` → `dev.event` (match TopicRegistry)
- [x] Add Strimzi KafkaTopic `dev.market_data` (5 partitions, 1-day retention)
- [x] Remove dead `KAFKA_EVENTS_TOPIC` env var from ingestion deployments
- [x] Remove dead `EVENTS_TOPIC` and `TOPIC_SIGNALS` env vars from strategy deployment
- [x] Add `ENVIRONMENT` env var to strategy deployment (needed by TopicRegistry)
- [x] Add `KAFKA_PRODUCER_OVERRIDES` to ingestion-historical (snappy + linger)
- [x] Add `KAFKA_PRODUCER_OVERRIDES` to simple-strategy (snappy + linger)
- [x] Update ConfigMap `EVENT_TOPIC` → `dev.event`

---

## Topic Layout (After Migration)

| Topic | Partitions | Key | Producers | Consumers |
|-------|-----------|-----|-----------|-----------|
| `dev-event` | 1 | `request_id` | strategies, ingestion | ingestion, strategies |
| `dev-market-data` | 5 | `symbol` | ingestion | strategies |
| `dev-market-data-historical-{id}` | auto | `symbol` | ingestion | strategies (ephemeral) |
| `dev-raw-signal` | 5 | `strategy_id:symbol` | strategies | risk, executor |
| `dev-execution-request` | 5 | `strategy_id:order_id` | risk | executor |
| `dev-execution-response` | 5 | `strategy_id:order_id` | executor | strategies |
| `dev-position-events` | 3 | `strategy_id` | executor | strategies |

**Naming**: `<env>-<name>` — hyphens only, no dots or underscores. K8s-safe.

## Consumer Group Design

| Service | Consumer Group | Notes |
|---------|---------------|-------|
| ingestion-hist | `ingestion-historical` | Shared group for load-balanced request processing |
| ingestion-stream | `ingestion-stream` | 1 replica only (Alpaca WS limit) |
| strategy-{N} | `strategy-{uuid}` | Unique group per pod for full fan-out of market_data |
| executor | `executor` | Shared group for exactly-once order processing |
| risk | `risk` | Shared group for exactly-once signal validation |

## Key Decisions

1. **No Avro migration in 2026** — JSON is sufficient for PoC scale. Add `schema_version` field to models for future-proofing.
2. **SDK is a toolbox, not a framework** — Each service composes its own TypedProducer/Consumer from SDK building blocks.
3. **`stream_data.alpaca` renamed to `market_data`** — broker-agnostic name, 5 partitions by default, partitioned by symbol.
4. **Receiver module removed from SDK** — The request/response correlation pattern is service-specific (ingestion->strategy communication). Each service that needs it implements a thin `RequestCorrelator`.
5. **EventBus removed from SDK** — Replaced by `TypedProducer[T]` / `TypedConsumer[T]` which work with any model type.
