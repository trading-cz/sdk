# LLM Context: Trading Platform Transport Redesign

## Current state (2026-05-27)

We just completed a full transport-layer redesign across 4 repos. Everything is pushed to feature branches with open PRs.

**Full plan**: https://github.com/trading-cz/sdk/blob/feature/kafka-confluence-changes/docs/transport-redesign-plan.md

## What changed — by repo

### SDK (`trading-cz/sdk` → PR #18, branch `feature/kafka-confluence-changes`)
- **New packages**: `serialization/` (Codec[T], JsonCodec[T]), `typed/` (TypedProducer[T], TypedConsumer[T])
- **New module**: `topics.py` (TopicRegistry, TopicConfig — replaces lost `tradingcz.kafka`)
- **Transport**: Rewrote `transport/kafka.py` → uses Confluent `AIOProducer`/`AIOConsumer` (native async, no executors). Consumer config is 100% overridable via `KAFKA_CONSUMER_OVERRIDES`.
- **Deleted**: `receiver/` (entire dir), `model/event_bus.py`, `tradingcz/kafka/` (orphaned .pyc)
- **Version**: 0.0.8 → 0.1.0
- **Dep removed**: `aiokafka` optional dep (no longer needed — Confluent has async now)

### Ingestion (`trading-cz/ingestion` → PR #27, branch `feature/kafka-infrastructure`)
- `EventBus` → `TypedConsumer[DataRequest]` + `TypedProducer[DataReady|DataError]`
- `stream_data.alpaca` → `dev-market-data` (5 partitions, symbol-keyed)
- `Topics`/`data_key()` → `TopicRegistry`/`TopicRegistry.partition_key()`
- SDK dep: v0.0.14 → v0.1.0

### Simple-Strategy (`trading-cz/simple-strategy` → PR #11, branch `feature/kafka-infrastructure`)
- `ConfluenceKafkaReceiverTransport` → `KafkaTransport` + `RequestCorrelator` (thin 90-LOC helper in `common/correlator.py`)
- Raw `confluent_kafka.Producer` → `TypedProducer[TradingSignal]`
- `confluent-kafka` removed from `pyproject.toml` deps
- Zero direct Kafka imports in strategy code

### Config (`trading-cz/config` → PR #27, branch `feature/kafka-transport-naming`)
- Strimzi topics: `dev-event` (1 partition), `dev-market-data` (5 partitions)
- Dead env vars removed from deployments
- Producer overrides activated (`snappy` + `linger.ms=5`)
- `auto.offset.reset` moved to `KAFKA_CONSUMER_OVERRIDES`

## Key conventions
- **Topic naming**: `<env>-<name>` — hyphens only, no dots (e.g. `dev-event`, `dev-market-data`)
- **Event topic**: 1 partition (total ordering for control plane)
- **Consumer config**: ALL librdkafka params via `KAFKA_CONSUMER_OVERRIDES` JSON env var — nothing hardcoded
- **No backward compat**: deprecated code deleted, not just warned

## Remaining work
- Step 4: Executor migration (colleague's project — deferred)
- Integration testing with real Kafka cluster
- Prod overlay configs

## Architecture (3-layer stack)
```
Layer 2: TypedProducer[T] / TypedConsumer[T]     ← services compose these
Layer 1: Serializer[T] / JsonCodec[T]             ← pluggable codec
Layer 0: Channel / Transport / KafkaTransport     ← byte pipes
```

## How services compose their Kafka setup
```python
# Every service owns its pipeline — SDK is just a toolbox:
transport = KafkaTransport(KafkaSettings())           # Layer 0
topics = TopicRegistry(env="dev")
events_ch = await transport.channel(topics.events.name)

# Layer 2 — typed, composable:
consumer = TypedConsumer(events_ch, JsonCodec(DataRequest))
producer = TypedProducer(events_ch, JsonCodec(DataReady),
                         key_fn=lambda e: e.request_id)

async for request in consumer.consume():              # natively async
    await producer.send(DataReady(...))
```

---
**Next task**: [PASTE YOUR STEP HERE]
