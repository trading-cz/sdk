# SDK Architectural Review — v2

**Date**: 2026-05-28 | **Reviewer**: Platform Architect | **Scope**: `trading-sdk` (Python 3.14+)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Assessment](#2-current-architecture-assessment)
3. [Critical Issues](#3-critical-issues)
4. [Missing Abstractions](#4-missing-abstractions)
5. [Leaky Abstractions](#5-leaky-abstractions)
6. [Duplication Analysis](#6-duplication-analysis)
7. [Proposed Final SDK Structure](#7-proposed-final-sdk-structure)
8. [Consumer API — The Ideal Experience](#8-consumer-api--the-ideal-experience)
9. [Performance & Design Patterns](#9-performance--design-patterns)
10. [Error Handling Strategy](#10-error-handling-strategy)
11. [Logging & Observability](#11-logging--observability)
12. [Async vs Sync Considerations](#12-async-vs-sync-considerations)
13. [Serialization & Schema Strategy](#13-serialization--schema-strategy)
14. [Testing Strategy](#14-testing-strategy)
15. [Migration Steps](#15-migration-steps)
16. [Documentation Structure](#16-documentation-structure)
17. [Validation Checklist](#17-validation-checklist)

---

## 1. Executive Summary

The SDK was recently rewritten and has **solid bones**. The transport layer is clean, the use of headers for metadata is the right call, and the decision to go concrete (Kafka-only, no abstract Transport) is pragmatic and correct.

However, there are **critical duplications**, **a missing protocol module**, **leaky abstractions at the business layer**, and **consumer-facing complexity** that prevents the SDK from achieving its primary goal: "using the SDK should feel like there is no Kafka at all."

**Bottom line**: The SDK is at ~70% of where it needs to be. The remaining 30% is not adding features — it's removing duplication, simplifying the API surface, being opinionated about defaults, and ensuring the `TradingApp` is the ONLY way users interact with the SDK.

---

## 2. Current Architecture Assessment

### 2.1 What's Working Well

| Component | Verdict |
|---|---|
| **KafkaMessage** — honest wrapper, no pretense | ✅ Perfect. Slots, frozen, carries what Kafka gives you. |
| **JsonCodec** — single-responsibility, generic | ✅ Clean. Pydantic-backed, one-codec-per-type. |
| **Headers as metadata, keys as routing** | ✅ Correct design. Headers carry type/source/seq; keys are plain strings. |
| **KafkaSettings** — env-first, escape hatches | ✅ Good. `producer_overrides`/`consumer_overrides` for librdkafka tuning. |
| **TopicRegistry** — single source of truth for names | ✅ Right idea, but overloaded (see §3.3). |
| **Murmur2 hash** — matches librdkafka | ✅ Necessary utility, correctly implemented. |
| **Error hierarchy** — `SdkError` root with subclasses | ✅ Good start, but under-used (see §10). |

### 2.2 What's Problematic

| Component | Issue | Severity |
|---|---|---|
| `_RequestReply` + `RequestReplyClient` | **Two implementations** of the same pattern | 🔴 Critical |
| `transport/protocol.py` module | **Does not exist** but is imported by consumers | 🔴 Critical |
| `_FireAndForget` manual header building | **Duplicate logic** with `message_headers.py` factories | 🟠 High |
| `TopicRegistry` builds JSON keys but keys are now strings | **Contradicts own design principle** | 🟠 High |
| `model/kafka_key.py` — deprecated but still imported | **Confusing** to developers | 🟠 High |
| `_DedupFilter` in `_helpers.py`, used only by `DataClient` | **Wrong placement** — should be a composable layer | 🟡 Medium |
| `TradingApp` not used by ANY consumer app | **Builder pattern is dead code in practice** | 🟡 Medium |
| `indicators/` package inside SDK | **Business logic in infrastructure layer** | 🟡 Medium |
| Header construction spread across 6+ places | **Fragile** — change one, miss another | 🟡 Medium |
| Auto-topic-creation in `KafkaTransport` | **Production anti-pattern** — should be IaC | 🟡 Medium |

---

## 3. Critical Issues

### 3.1 CRITICAL: Duplicate Request/Reply Implementations

Two classes do the same thing but with different APIs:

| | `_RequestReply` (`_helpers.py`) | `RequestReplyClient` (`transport/request_reply.py`) |
|---|---|---|
| Location | `tradingcz.sdk._helpers` (internal) | `tradingcz.transport.request_reply` (public) |
| Serialization | Hardcoded `model_dump_json()` / `model_validate_json()` | Pluggable `Serializer[Req]` / `Deserializer[Resp]` |
| Type registry | `register_type(message_type, model)` | Type-safe generics `[Req, Resp]` |
| ID extraction | `getattr(obj, "request_id")` — convention | `request_id_of` callable — explicit |
| Status | Used by `DataClient`, `PositionClient`, etc. | Used by simple-strategy directly |

**Verdict**: `RequestReplyClient` is the better design (pluggable, generic, explicit). `_RequestReply` exists only because `DataClient` wanted Pydantic-specific convenience. **Pick one and delete the other.**

### 3.2 CRITICAL: Missing `tradingcz.transport.protocol` Module

The `summary-sdk-changes.md` documents:
```python
from tradingcz.transport import Channel, Transport, Message  # from protocol.py
```
And consumer apps (ingestion, simple-strategy) import:
```python
from tradingcz.transport.protocol import Channel, Transport
```

**But `tradingcz/transport/protocol.py` does not exist.** It was either never created or was deleted. The `serialization/protocol.py` file exists but is about codecs, not transport abstractions.

**Impact**: Any app that follows the documented import path will fail at runtime.

**Fix**: Either create the module with `Channel`/`Transport`/`Message` abstracts, or delete all references and be explicit that Kafka is the only transport.

### 3.3 HIGH: TopicRegistry Builds JSON Keys But Keys Are Now Plain Strings

The `TopicRegistry` has methods `event_key()` and `market_data_key()` that produce JSON strings like:
```python
'{"event_type":"data_request","source":"smoke_test","request_id":"abc123"}'
```

But the design doc in `message_headers.py` says:
> **Key = routing only** — plain string (e.g. "AAPL"), not JSON.

These methods import from the **deprecated** `model/kafka_key.py` module. This is internally inconsistent and confusing. Either:
- **Option A**: Delete the JSON key methods. Keys are plain strings. Period.
- **Option B**: Keep them but rename to `event_key_json()` and move to a dedicated key-schema module with a clear rationale.

**Recommendation**: Option A. Plain string keys are simpler, faster, and easier to debug with `kcat`.

### 3.4 HIGH: Header Construction Scattered Across 6+ Locations

Headers are built in at least these places:
1. `_FireAndForget.send()` — manual dict construction
2. `_RequestReply._request()` — manual dict construction
3. `TypedProducer` via `headers_fn` — caller-provided
4. `message_headers.event_headers()` — factory function
5. `message_headers.market_data_headers()` — factory function
6. `message_headers.historical_headers()` — factory function
7. `DataClient._stream()` — reads headers manually
8. `DataClient.request_historical()` — reads headers manually

This means header field names like `"source_app"` vs `"source"` are duplicated and can drift. There's no single source of truth.

---

## 4. Missing Abstractions

### 4.1 No `MessageEnvelope` / Outgoing Message Builder

Every producer manually builds `{payload, key, headers}`. There should be a single `OutgoingMessage` or `Envelope` that:
- Always carries `message_type`, `source_app`, `schema_version`, `sequence`
- Auto-increments sequence numbers
- Computes the correct partition key
- Is used by EVERYTHING that sends a message

### 4.2 No Input Validation Layer

`DataClient` receives raw bytes and trusts `model_validate_json()`. There's no:
- Schema version check on incoming messages
- Validation that required headers are present
- Rejection of messages from unknown sources

### 4.3 No Health/Metrics Endpoint Abstraction

The old architecture had `BaseServer` with Prometheus setup. The SDK should provide a standard health-check and metrics client, not force every app to wire it manually.

### 4.4 No Retry / Circuit Breaker

Kafka can fail. Currently there's no retry policy, no backoff, no circuit breaker. The `_RequestReply` listener crashes silently and rejects all pending futures — callers just get `RuntimeError("listener crashed")` with no recovery path.

### 4.5 No Structured Logging Context

Every module uses `logging.getLogger(__name__)` but there's no standard way to add `service_id`, `request_id`, or `trace_id` to log records. Structured logging context should be built into the SDK.

---

## 5. Leaky Abstractions

### 5.1 `KafkaMessage` Leaks Through `DataClient`

The `DataClient` API is supposed to hide Kafka:
```python
bars = await app.data.request_historical(["AAPL"])
```

But internally, `DataClient` inspects raw `KafkaMessage.headers`:
```python
if msg.headers.get("request_id") != req.request_id:
    continue
if self._dedup.is_duplicate(
    msg.headers.get("source", msg.headers.get("source_app", "")),
    msg.headers.get("sequence", "0"),
):
```

The `DataClient` knows about Kafka headers, sequence numbers, and dedup keys. This is a leak. The transport layer should handle dedup and filtering; the business layer should just see a stream of `Bar` objects.

### 5.2 `TopicRegistry` is Half Config, Half Logic

`TopicRegistry` does three things:
1. Topic name templates (`f"{env}-event"`)
2. Topic creation config (partitions, retention)
3. Key generation logic (JSON builders)

This mixes declarative config with procedural logic. A topic registry should be pure config. Key generation should be a separate concern (and is largely obsolete with plain string keys).

### 5.3 `_DedupFilter` is in `_helpers.py` But is a First-Class Concern

Deduplication is not a "helper" — it's a core reliability concern. It should be:
- A named, public module (`tradingcz.sdk.dedup` or `tradingcz.transport.dedup`)
- Composable (attach to any consumer)
- Configurable (per-topic, per-message-type)

---

## 6. Duplication Analysis

### 6.1 What Lives in ingestion That Should Be in SDK

| Code in ingestion | Should move to SDK as | Rationale |
|---|---|---|
| `ingestion/settings.py` extending `KafkaSettings` | SDK provides standard `IngestionSettings`, `StrategySettings`, `ExecutorSettings` | Every app re-implements the same settings pattern |
| `ingestion/handlers/router.py` — `TypedConsumer` + dispatch loop | `tradingcz.sdk.MessageRouter` | Generic typed dispatch on the event topic |
| `ingestion/handlers/stream.py` — subscribe/unsubscribe lifecycle | `tradingcz.sdk.StreamManager` | Streaming lifecycle management is reusable |
| `ingestion/handlers/historical.py` — `TypedProducer[DataReady]` pattern | Already exists as `_FireAndForget` but should be public | Response publishing pattern |
| `ingestion/adapters/protocol.py` — abstract provider interface | `tradingcz.sdk.provider` | Market data adapter protocol |

### 6.2 What Lives in simple-strategy That Should Be in SDK

| Code in simple-strategy | Should move to SDK as | Rationale |
|---|---|---|
| Manual `RequestReplyClient[DataRequest, DataReady\|DataError]` construction | `TradingApp.data.request_historical()` | Already exists but strategies aren't using it |
| Manual `TypedProducer[TradingSignal]` + `JsonCodec(TradingSignal)` | `TradingApp.signals.publish()` | Already exists but strategies aren't using it |
| `Deserializer` implementation for `DataReady\|DataError` union | `tradingcz.serialization.UnionCodec` | Generic union deserialization |
| ATR calculation in `pcb_breakout/` | Already in SDK as `indicators.atr` | Already centralized |

### 6.3 Key Insight: Strategies Don't Use `TradingApp`

The simple-strategy code does NOT use `TradingApp`. Instead, it manually wires:
```python
transport = KafkaTransport(kafka)
topics = TopicRegistry(env="dev")
# ... 50 lines of manual wiring ...
async with RequestReplyClient[...](...) as client:
    response = await client.request(data_request)
```

This is 60+ lines of boilerplate that `TradingApp` should eliminate. The fact that strategies bypass `TradingApp` means either:
1. `TradingApp` doesn't provide enough value, OR
2. Strategies were written before `TradingApp` existed, OR
3. The `TradingApp` API is not discoverable

**All three are likely true.** The fix is to make `TradingApp` so obviously valuable that no one would consider bypassing it.

---

## 7. Proposed Final SDK Structure

```
tradingcz/
├── __init__.py                    # SCHEMA_VERSION, namespace package
├── py.typed
│
├── _version.py                    # __version__ = "1.0.0"  (single source)
│
├── errors.py                      # SdkError hierarchy (CLEAN — see §10)
│
├── config/
│   ├── __init__.py                # KafkaSettings, LoggingSettings, AppSettings
│   └── settings.py
│
├── model/                         # Domain models — ZERO dependencies on transport
│   ├── __init__.py
│   ├── market/                    # was "ingestion/" — clearer name
│   │   ├── __init__.py
│   │   ├── bar.py                 # Bar (frozen, slots via Pydantic)
│   │   ├── quote.py               # Quote
│   │   ├── trade.py               # Trade
│   │   ├── snapshot.py            # Snapshot
│   │   └── stream_quote.py        # StreamQuote
│   ├── signal/
│   │   ├── __init__.py
│   │   └── models.py              # TradingSignal (flattened — no envelope cruft)
│   ├── events/
│   │   ├── __init__.py
│   │   ├── data.py                # DataRequest, DataReady, DataError
│   │   └── service.py             # ServiceRequest
│   ├── order/
│   │   ├── __init__.py
│   │   ├── limit.py               # LimitOrder
│   │   └── market.py              # MarketOrder
│   ├── enum/
│   │   ├── __init__.py
│   │   ├── timeframe.py
│   │   ├── order.py               # OrderSide, OrderType, OrderClass, TimeInForce
│   │   └── adjustment.py
│   └── headers.py                 # Header field CONSTANTS (single source of truth)
│                                   #   MSG_TYPE = "message_type"
│                                   #   SOURCE_APP = "source_app"
│                                   #   REQUEST_ID = "request_id"
│                                   #   SEQUENCE = "sequence"
│                                   #   SCHEMA_VERSION = "schema_version"
│                                   #   etc.
│                                   # Plus one factory: make_headers(**kwargs) -> dict[str,str]
│
├── codec/                         # was "serialization/" — shorter, clearer
│   ├── __init__.py
│   ├── _protocol.py               # Serializer[T], Deserializer[T], Codec[T]  (private)
│   └── json_codec.py              # JsonCodec[T]
│
├── transport/                     # All Kafka in kafka/ — no abstract transport
│   ├── __init__.py
│   ├── _message.py                # KafkaMessage  (private — users don't import this)
│   ├── _hash.py                   # murmur2, partition_for  (private)
│   ├── _dedup.py                  # DedupFilter  (private, composable)
│   ├── envelope.py                # OutgoingEnvelope — THE way to build a message
│   │                               #   envelope = Envelope(
│   │                               #       payload=signal,
│   │                               #       message_type="trading_signal",
│   │                               #       key=signal.symbol,
│   │                               #       source_app="my-strategy",
│   │                               #   )
│   │                               #   await channel.send(envelope)
│   └── kafka/
│       ├── __init__.py
│       ├── _channel.py            # KafkaChannel (private constructor, via KafkaTransport)
│       ├── _transport.py          # KafkaTransport (private constructor, via TradingApp)
│       └── _topics.py             # TopicRegistry (pure config, no key builders)
│
├── sdk/                           # PUBLIC API — the ONLY thing users import
│   ├── __init__.py                # TradingApp, DataClient, SignalPublisher, ...
│   ├── _app.py                    # TradingApp builder
│   ├── _data.py                   # DataClient
│   ├── _signals.py                # SignalPublisher
│   ├── _positions.py              # PositionClient
│   ├── _balance.py                # BalanceClient
│   ├── _orders.py                 # OrderClient
│   ├── _router.py                 # MessageRouter — typed dispatch from event topic
│   └── _health.py                 # HealthClient — liveness/readiness probes
│
└── indicators/                    # Move to separate package or keep minimal
    ├── __init__.py
    └── atr.py                     # calculate_atr
```

### Key Structural Changes

| Before | After | Rationale |
|---|---|---|
| `tradingcz.model.ingestion/` | `tradingcz.model.market/` | "ingestion" is a service, not a model category |
| `tradingcz.model.signal.py` (monolithic) | `tradingcz.model.signal/models.py` | Flattened, remove `SignalEnvelope`/`SignalKey`/`SignalValue` cruft |
| `tradingcz.model.events.py` (monolithic) | `tradingcz.model.events/{data,service}.py` | Split control-plane from service requests |
| `tradingcz.model.message_headers.py` | `tradingcz.model.headers.py` | Header field constants + ONE factory, no Pydantic header models |
| `tradingcz.serialization/` | `tradingcz.codec/` | Shorter, more descriptive |
| `tradingcz.transport/kafka_message.py` | `tradingcz.transport/_message.py` | Users never import KafkaMessage directly |
| `tradingcz.transport/stream.py` | Merged into `transport/` | `TypedProducer`/`TypedConsumer` are transport concerns |
| `tradingcz.transport/request_reply.py` | Merged into `sdk/_app.py` or deleted | Only ONE request/reply implementation |
| `tradingcz.transport/hash.py` | `tradingcz.transport/_hash.py` | Implementation detail |
| Multiple header Pydantic models | `tradingcz.model.headers.py` — constants only | Headers are `dict[str,str]` — Pydantic models add ceremony with no value |
| `_FireAndForget`, `_RequestReply` in `_helpers.py` | `tradingcz.sdk._router.py` | Request/reply is a first-class SDK concern |

---

## 8. Consumer API — The Ideal Experience

### 8.1 Strategy App (the primary consumer)

**Today** (60+ lines of boilerplate):
```python
kafka = KafkaSettings(bootstrap_servers="...", consumer_group="...")
transport = KafkaTransport(kafka)
topics = TopicRegistry(env="dev")
events_channel = await transport.channel(topics.events.name)

# Build request/reply client
async with RequestReplyClient[DataRequest, DataReady | DataError](
    channel=events_channel,
    request_serializer=JsonCodec(DataRequest),
    response_deserializer=data_response_deserializer,
    request_id_of=lambda r: r.request_id,
    response_id_of=lambda r: r.request_id,
    key_fn=lambda r: r.request_id,
    headers_fn=event_headers_fn,
) as client:
    response = await client.request(data_request)
    # ... open another channel, consume bars, etc.
```

**Ideal** (~5 lines):
```python
from tradingcz.sdk import TradingApp

app = await TradingApp.create(env="dev", service_id="my-strategy")

# Historical data — one call, sorted, deduplicated
bars = await app.data.request_historical(["AAPL"], days=14)
atr = calculate_atr(bars["AAPL"], period=3)

# Streaming — async iterator, no channel management
async for quote in app.data.stream_quotes(["AAPL"]):
    if meets_condition(quote):
        break

# Signals — one call, fire and forget
await app.signals.publish(TradingSignal(
    symbol="AAPL", side="LONG", entry_price=151.0, ...
))

# Positions — one call
positions = await app.positions.get()

await app.close()
```

### 8.2 Ingestion Service (the data provider)

**Ideal**:
```python
from tradingcz.sdk import IngestionApp

app = await IngestionApp.create(env="dev", broker="alpaca")

# Listen for data requests, respond automatically
await app.serve_data_requests(
    historical_handler=my_historical_handler,
    stream_handler=my_stream_handler,
)
```

### 8.3 Design Principles for the Consumer API

1. **One import**: `from tradingcz.sdk import TradingApp` is all you need.
2. **No transport imports**: Users NEVER import `KafkaChannel`, `KafkaTransport`, `TopicRegistry`, `TypedProducer`, `TypedConsumer`, `KafkaSettings`, `JsonCodec`, `KafkaMessage`.
3. **No header construction**: Headers are built internally. Users provide domain data only.
4. **No topic knowledge**: Users don't know about `dev-event`, `dev-market-data`, etc.
5. **No serialization knowledge**: JSON is the default. Override only if you need Avro/Protobuf.
6. **Context manager or explicit close**: `async with TradingApp(...) as app:` or `await app.close()`.
7. **Type-safe returns**: `app.data.request_historical()` returns `dict[str, list[Bar]]`. `app.signals.publish()` takes `TradingSignal`. No `Any`, no `object`, no casts.

---

## 9. Performance & Design Patterns

### 9.1 Sync Producer + `run_in_executor` — Is This OK?

**Current approach** (`KafkaChannel.send()`):
```python
def _produce_and_flush() -> None:
    self._producer.produce(...)
    remaining = self._producer.flush(timeout=30)
    ...
loop = asyncio.get_running_loop()
await loop.run_in_executor(None, _produce_and_flush)
```

**Assessment**: This is correct for the current usage pattern (low-frequency control messages). For high-throughput market data streaming (thousands of messages/second), this is a bottleneck:
- `flush()` blocks the executor thread for up to 30 seconds
- Each send ties up a thread pool worker
- The default `ThreadPoolExecutor` has limited workers

**Recommendation**: Keep this for control-plane messages (events topic). For data-plane streaming, provide an **async batch send**:
```python
async def send_batch(self, messages: list[Envelope]) -> None:
    """Send multiple messages with a single flush."""
    for msg in messages:
        self._producer.produce(...)  # queue only, no flush
    await loop.run_in_executor(None, self._producer.flush, 30)
```

Or use `confluent_kafka`'s delivery callback + `poll()` for truly async sends.

### 9.2 Topic Auto-Creation is an Anti-Pattern

`KafkaTransport._ensure_topic()` creates topics via Admin API at runtime. This:
- Requires admin privileges on the Kafka cluster
- Bypasses infrastructure-as-code (the `config/` repo)
- Creates topics with inconsistent configs across environments
- Fails silently if the broker doesn't allow auto-creation

**Recommendation**: Remove auto-creation. Require topics to exist. Provide a CLI tool for topic creation:
```bash
sdk-cli topics create --env dev
```

### 9.3 Consumer Group Naming

Current: `f"{consumer_group}-{topic}"` → One app creates multiple consumer groups.

**Recommendation**: One consumer group per app. Use `KafkaChannel` with shared consumer, not one consumer per channel:
```python
# One consumer, subscribed to multiple topics
consumer = AIOConsumer({... "group.id": service_id})
consumer.subscribe(["dev-event", "dev-market-data", "dev-raw-signal"])
```

This simplifies offset management and makes it clear what "one app" means in Kafka terms.

### 9.4 Memory: `_DedupFilter` Bounds

Current: LRU with default `max_size=100_000`. Fine for most cases. But:
- Per-(source, sequence) key means one bad source can evict good entries
- No per-topic isolation

**Recommendation**: Make dedup optional and per-topic:
```python
app = TradingApp(...).with_dedup(max_per_topic=50_000).build()
```

---

## 10. Error Handling Strategy

### 10.1 Current Error Hierarchy

```
SdkError
├── TransportError
│   ├── ConnectionError
│   ├── TimeoutError
│   └── TopicNotFoundError
├── SerializationError
├── ConfigurationError
└── MessageTypeError
```

**Problems**:
1. `TimeoutError` shadows Python's built-in `TimeoutError` (used by `asyncio.wait_for`)
2. `ConnectionError` shadows Python's built-in `ConnectionError`
3. No `ValidationError` for malformed messages
4. No `DedupError` or `SequenceError` for gap detection
5. Errors are defined but rarely raised — `DataClient` raises bare `RuntimeError`

### 10.2 Proposed Error Hierarchy

```python
class SdkError(Exception): ...

# Transport
class TransportError(SdkError): ...
class BrokerUnreachableError(TransportError): ...    # was ConnectionError
class RequestTimeoutError(TransportError): ...       # was TimeoutError
class TopicNotFoundError(TransportError): ...

# Data
class DataError(SdkError): ...
class NoDataAvailableError(DataError): ...
class InvalidDataError(DataError): ...

# Messaging
class MessagingError(SdkError): ...
class SerializationError(MessagingError): ...
class UnknownMessageTypeError(MessagingError): ...   # was MessageTypeError
class DuplicateMessageError(MessagingError): ...     # new — dedup hit (info, not error)

# Configuration
class ConfigurationError(SdkError): ...

# Application
class AppError(SdkError): ...
class AppNotBuiltError(AppError): ...                # call .build() first
class AppAlreadyClosedError(AppError): ...
```

### 10.3 Error Handling Policy

1. **Never raise generic `RuntimeError` or `Exception`** — always use SDK error types.
2. **Always attach context**: request_id, symbol, topic name.
3. **Log before raising**: Include all relevant fields in the log message.
4. **Provide recovery hints**: Error messages should tell the user what to do.
5. **Don't silently swallow**: `except Exception: continue` should be `except (ValueError, json.JSONDecodeError): logger.debug(...); continue`.

---

## 11. Logging & Observability

### 11.1 Current State

Each module uses `logging.getLogger(__name__)`. That's it. No structured context.

### 11.2 Proposed: Structured Logging Context

```python
# tradingcz/sdk/_logging.py
import logging
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_symbol: ContextVar[str] = ContextVar("symbol", default="")

class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = {
            "request_id": _request_id.get(),
            "symbol": _symbol.get(),
            "service_id": self.extra.get("service_id", ""),
        }
        return f"[{extra['service_id']}] {msg}", {"extra": extra}
```

Usage:
```python
logger = get_context_logger(__name__, service_id="my-strategy")
# → [my-strategy] Requesting historical bars for AAPL
```

### 11.3 Prometheus Metrics

The SDK should provide built-in metrics:
- `sdk_messages_sent_total{topic, message_type}` — counter
- `sdk_messages_received_total{topic, message_type}` — counter
- `sdk_request_duration_seconds{request_type}` — histogram
- `sdk_dedup_skipped_total{topic}` — counter
- `sdk_errors_total{error_type}` — counter
- `sdk_kafka_connection_status` — gauge (0/1)

---

## 12. Async vs Sync Considerations

### 12.1 Current State

Everything is async (`async def`). This is correct for an I/O-bound messaging system.

### 12.2 Issues

1. **`run_in_executor` for every send**: Thread pool exhaustion under load.
2. **No sync escape hatch**: What if someone wants to use the SDK in a sync context (CLI tool, Lambda)?

### 12.3 Recommendations

1. **Batch sends** for high-throughput (see §9.1).
2. **Provide a sync wrapper** for CLI/simple use cases:
   ```python
   from tradingcz.sdk import sync

   with sync.TradingApp(env="dev", service_id="cli-tool") as app:
       bars = app.data.request_historical(["AAPL"], days=5)
   ```
3. **Document the async requirement clearly**: "This SDK is async-first. Use `asyncio.run()` for sync contexts."

---

## 13. Serialization & Schema Strategy

### 13.1 Current State

- `JsonCodec[T]` — the only codec. Good.
- `SCHEMA_VERSION = "1.0"` embedded in every message header. Good.
- No schema registry, no version negotiation.

### 13.2 Recommendations

1. **Keep JSON as the only wire format** until there's a proven need for Avro/Protobuf.
2. **Add schema version checking on receive**: If `schema_version` header != `SCHEMA_VERSION`, log a warning (don't reject — be lenient in what you accept).
3. **Provide schema documentation** generated from Pydantic models:
   ```bash
   sdk-cli schema > schema.json
   ```
4. **The Pydantic models ARE the schema**. No separate `.proto` or `.avsc` files.

---

## 14. Testing Strategy

### 14.1 Current State

One file: `smoke_test.py` — 8 integration tests against a real Kafka broker.

### 14.2 Proposed Test Suite

```
tests/
├── unit/
│   ├── test_dedup.py               # DedupFilter
│   ├── test_envelope.py            # OutgoingEnvelope
│   ├── test_headers.py             # Header constants, make_headers()
│   ├── test_codec.py               # JsonCodec round-trip
│   ├── test_hash.py                # murmur2, partition_for
│   ├── test_errors.py              # Error hierarchy, context
│   ├── test_models.py              # Model validation (all Pydantic models)
│   ├── test_header_dispatch.py     # Message type → model dispatch
│   ├── test_request_reply.py       # RequestReplyClient (mocked channel)
│   ├── test_data_client.py         # DataClient (mocked transport)
│   └── test_signal_publisher.py    # SignalPublisher (mocked channel)
├── integration/
│   ├── conftest.py                 # Kafka fixture (testcontainers or docker-compose)
│   ├── test_kafka_channel.py       # Real Kafka send/receive
│   ├── test_typed_producer.py      # Real Kafka typed round-trip
│   ├── test_request_reply_e2e.py   # Real Kafka request/reply
│   ├── test_trading_app.py         # Real Kafka TradingApp lifecycle
│   └── test_dedup_e2e.py           # Real Kafka dedup
└── smoke/
    └── smoke_test.py               # Current smoke test (keep, but refactor)
```

### 14.3 Required Test Infrastructure

- **`pytest-asyncio`** — already in dev deps
- **`testcontainers[kafka]`** or **`docker-compose`** for integration tests
- **CI pipeline**: Run unit tests always, integration tests on PR to main

---

## 15. Migration Steps

### 15.1 Phase 1: SDK Cleanup (Week 1-2)

1. **Delete `_RequestReply`** from `_helpers.py`. Keep only `transport/request_reply.py`'s `RequestReplyClient`.
2. **Create `tradingcz/model/headers.py`** — single source of header field names + `make_headers()` factory.
3. **Delete `model/kafka_key.py`** — it's deprecated and misleading.
4. **Delete `model/message_headers.py`** — replace with `headers.py`.
5. **Delete `TopicRegistry.event_key()` and `market_data_key()`** — keys are plain strings.
6. **Create `tradingcz/transport/_protocol.py`** or **delete all references** to the non-existent `transport.protocol` module.
7. **Move `_DedupFilter`** to `tradingcz/transport/_dedup.py` (keep internal for now).
8. **Rename** `serialization/` → `codec/`.
9. **Rename** `model/ingestion/` → `model/market/`.
10. **Flatten** `model/signal.py` — remove `SignalEnvelope`, `SignalKey`, `SignalValue`, `build_signal`. Keep only `TradingSignal`.

### 15.2 Phase 2: Consumer API Simplification (Week 3)

1. **Redesign `TradingApp`** to eliminate all transport imports from user code.
2. **Add `Envelope`** builder — single way to construct outgoing messages.
3. **Unify request/reply** — `TradingApp` uses `RequestReplyClient` internally.
4. **Add `app.data.stream_quotes()`** — async iterator, no channel management.
5. **Add `app.health`** — standard health check client.
6. **Remove auto-topic-creation** — topics must exist.

### 15.3 Phase 3: Consumer App Migration (Week 4)

1. **simple-strategy**: Replace all manual wiring with `TradingApp`.
2. **ingestion**: Create `IngestionApp` subclass or configure `TradingApp` for provider mode.
3. **executor**: Wire to new SDK (currently has no SDK imports — easy).

### 15.4 Phase 4: Polish (Week 5)

1. **Add structured logging context**.
2. **Add Prometheus metrics**.
3. **Write unit tests** for all core modules.
4. **Write integration tests** with real Kafka.
5. **Generate API documentation** from docstrings.

---

## 16. Documentation Structure

All existing MD files in `docs/` and `doc/` are obsolete. Delete them all. Replace with:

```
README.md                   # Quickstart: 30-second "Hello World"
docs/
├── index.md                # Documentation hub
├── getting-started.md      # 5-minute tutorial
├── concepts.md             # Architecture overview (topics, headers, message types)
├── api/
│   ├── trading-app.md      # TradingApp reference
│   ├── data-client.md      # DataClient — historical + streaming
│   ├── signal-publisher.md # SignalPublisher
│   ├── position-client.md  # PositionClient
│   ├── balance-client.md   # BalanceClient
│   ├── order-client.md     # OrderClient
│   └── health-client.md    # HealthClient
├── models/
│   ├── market-data.md      # Bar, Quote, Trade, StreamQuote, Snapshot
│   ├── signals.md          # TradingSignal
│   └── events.md           # DataRequest, DataReady, DataError, ServiceRequest
├── guides/
│   ├── writing-a-strategy.md    # How to write a strategy with the SDK
│   ├── writing-a-provider.md    # How to write a data provider with the SDK
│   └── production-checklist.md  # Before going to prod
├── reference/
│   ├── topic-naming.md          # Topic naming convention
│   ├── header-fields.md         # All header fields and their meanings
│   ├── error-codes.md           # Error types and recovery
│   └── versioning.md            # Schema versioning policy
└── migration/
    └── v1-guide.md              # Migration from old SDK
```

---

## 17. Validation Checklist

Before declaring the SDK "done", verify every item:

### Architecture
- [ ] Only ONE request/reply implementation exists
- [ ] Only ONE way to build outgoing message headers
- [ ] `TopicRegistry` has no JSON key builders
- [ ] No deprecated modules (`kafka_key.py`, `message_headers.py` with Pydantic models)
- [ ] `transport/` has no abstract `Channel`/`Transport` (Kafka is permanent)

### Consumer API
- [ ] `TradingApp` is the ONLY public import from `tradingcz.sdk`
- [ ] Users NEVER import from `tradingcz.transport`
- [ ] Users NEVER import from `tradingcz.serialization`
- [ ] Users NEVER construct `KafkaSettings` manually
- [ ] `app.data.request_historical()` returns `dict[str, list[Bar]]`
- [ ] `app.data.stream_quotes()` yields `StreamQuote` objects
- [ ] `app.signals.publish(signal)` is fire-and-forget
- [ ] `app.positions.get()` returns `list[Position]`
- [ ] `app.close()` or `async with` cleans up all resources

### Performance
- [ ] Batch send for data-plane messages
- [ ] Dedup is optional and configurable
- [ ] No auto-topic-creation at runtime
- [ ] Consumer group naming is consistent (one per app)

### Error Handling
- [ ] No bare `RuntimeError` or `Exception` raises
- [ ] All errors are SDK error types
- [ ] Errors carry context (request_id, symbol, topic)
- [ ] Timeout errors are distinct from Python's built-in `TimeoutError`

### Logging & Observability
- [ ] Structured logging with service_id, request_id, symbol context
- [ ] Prometheus metrics for sends, receives, latency, errors, dedup
- [ ] Health check endpoint or client

### Testing
- [ ] Unit tests for DedupFilter, Envelope, headers, codec, hash
- [ ] Unit tests for model validation
- [ ] Unit tests with mocked channel for DataClient, SignalPublisher, etc.
- [ ] Integration tests with real Kafka
- [ ] Smoke test (keep current one, refactored)

### Documentation
- [ ] README.md has a working 30-second example
- [ ] All public methods have docstrings
- [ ] Migration guide for existing apps
- [ ] No obsolete MD files in `docs/` or `doc/`

---

## Appendix A: Example — The Ideal Strategy

```python
"""
my_strategy.py — ATR(3) breakout strategy using the trading SDK.

Usage:
    export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
    python my_strategy.py
"""

import asyncio
from tradingcz.sdk import TradingApp
from tradingcz.model import TradingSignal
from tradingcz.indicators import calculate_atr


async def main():
    # One-liner to set up everything — Kafka, topics, channels, serializers.
    async with TradingApp(env="dev", service_id="atr3-breakout") as app:

        # Request 14 days of daily bars. Returns {symbol: [Bar]}.
        # Dedup, ordering, error handling — all handled internally.
        bars = await app.data.request_historical(["AAPL", "TSLA"], days=14)

        for symbol, symbol_bars in bars.items():
            # Pure function — no I/O, no Kafka.
            atr = calculate_atr(symbol_bars, period=3)
            last_close = symbol_bars[-1].close
            entry = last_close + atr
            stop = last_close - atr

            # Publish signal. Fire-and-forget.
            # Kafka key, headers, serialization — all automatic.
            await app.signals.publish(TradingSignal(
                symbol=symbol,
                side="LONG" if entry > last_close else "SHORT",
                strategy_id="atr3-breakout",
                open_price=last_close,
                entry_price=entry,
                stop_loss=stop,
            ))

        # Optionally: stream live quotes and adjust
        # async for quote in app.data.stream_quotes(["AAPL"]):
        #     ...


if __name__ == "__main__":
    asyncio.run(main())
```

**This is the target.** 8 lines of SDK interaction. Zero transport knowledge. Zero Kafka imports. The user focuses exclusively on their trading logic.

---

## Appendix B: Header Field Constants (Single Source of Truth)

```python
# tradingcz/model/headers.py
"""Canonical Kafka header field names.

Every module that builds or reads Kafka headers MUST use these constants.
No string literal header names anywhere else in the codebase.
"""

# ── Standard (present on all messages) ──────────────────────────────────────
MESSAGE_TYPE    = "message_type"      # e.g. "data_request", "trading_signal"
SOURCE_APP      = "source_app"        # e.g. "ingestion", "my-strategy"
SCHEMA_VERSION  = "schema_version"    # e.g. "1.0"
SEQUENCE        = "sequence"          # monotonic per (source_app, topic)

# ── Event topic ─────────────────────────────────────────────────────────────
REQUEST_ID      = "request_id"        # correlation ID for request/reply
TRACKING_ID     = "tracking_id"       # run identifier for signal correlation
STRATEGY_ID     = "strategy_id"       # strategy that produced a signal

# ── Market data ─────────────────────────────────────────────────────────────
SOURCE          = "source"            # origin service (e.g. "ingestion")
BROKER          = "broker"            # e.g. "alpaca"
SYMBOL          = "symbol"            # ticker symbol


def make_headers(
    *,
    message_type: str,
    source_app: str = "",
    schema_version: str = "1.0",
    sequence: int = 0,
    **extra: str,
) -> dict[str, str]:
    """Build a standard headers dict.

    All modules that produce Kafka messages MUST use this function.
    Extra kwargs become additional header fields (e.g. request_id, symbol).
    """
    return {
        MESSAGE_TYPE: message_type,
        SOURCE_APP: source_app,
        SCHEMA_VERSION: schema_version,
        SEQUENCE: str(sequence),
        **extra,
    }
```

This single module replaces ALL of:
- `model/message_headers.py` (Pydantic models + 3 factory functions)
- `model/kafka_key.py` (deprecated aliases)
- Manual dict construction in `_FireAndForget`, `_RequestReply`, `TopicRegistry`, `DataClient`
- `headers_fn` lambdas in strategy code

Every producer imports from ONE place:
```python
from tradingcz.model.headers import make_headers, MESSAGE_TYPE, SOURCE_APP
```

Every consumer reads from ONE place:
```python
from tradingcz.model.headers import REQUEST_ID, SYMBOL
msg.headers.get(REQUEST_ID, "")
```
