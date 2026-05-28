# SDK Simplification Proposal

> **Date:** 2026-05-28
> **Scope:** `trading-sdk` repository
> **Key constraint change:** Kafka is the permanent transport. No switching to REST/gRPC/WS.
> **Goals:** Simplicity, easy business-level API, high performance, clean layering.

---

## Table of Contents

1. [Response to Previous Analysis Feedback](#response-to-previous-analysis-feedback)
2. [Core Design Principles (Revised)](#core-design-principles-revised)
3. [What Gets Removed](#what-gets-removed)
4. [What Gets Simplified](#what-gets-simplified)
5. [Proposed Architecture](#proposed-architecture)
6. [Public API — The "Business Layer"](#public-api--the-business-layer)
7. [Migration Path](#migration-path)
8. [Before/After Comparison](#beforeafter-comparison)

---

## Response to Previous Analysis Feedback

### Point (a): `Message` should NOT carry `offset`, `partition`, `topic`

**You are correct.** Adding Kafka-internal fields (`offset`, `partition`, `topic`) to a generic `Message` dataclass violates the abstraction. Those fields have no meaning outside Kafka.

**Revised position:**

If we accept Kafka as the only transport, the `Message` dataclass and the `Channel`/`Transport` ABCs become unnecessary indirection. We should work with Kafka-native types directly:

- `KafkaChannel.send()` and `KafkaChannel.receive()` use Kafka's own message types
- Metadata like `offset` and `partition` are accessed through Kafka-specific paths when needed (e.g., `KafkaMessage.offset`)
- Consumers that need offset tracking get it from a Kafka-aware wrapper, not from a pretend-generic type

**What IS transport-agnostic and worth keeping:**
- `headers: dict[str, str]` — every messaging system has metadata
- `key: str` — most messaging systems have a routing key concept
- `payload: bytes` — universal

But we don't need a `Message` dataclass to enforce this. We can just pass these as parameters to `send()` and yield them from `receive()`.

---

## Core Design Principles (Revised)

| Principle | What it means |
|-----------|---------------|
| **Kafka is the substrate** | No abstract transport layer. `KafkaChannel` and `KafkaTransport` are the concrete foundation. |
| **Users write business logic, not plumbing** | SDK consumers import ONE thing, call ONE setup, and get typed business-level APIs. Zero Kafka knowledge required. |
| **Power users can go deeper** | The lower-level `TypedProducer`/`TypedConsumer`/`KafkaChannel` are still public for advanced use cases. |
| **Keep serialization abstract** | `Serializer[T]`/`Deserializer[T]`/`Codec[T]` ABCs stay — they're pure data conversion, no transport dependency. |
| **Headers are first-class** | Every `send()` accepts optional `headers: dict[str, str]`. Metadata lives in headers, not in JSON keys. |
| **Keys are for routing only** | Plain strings (`"AAPL"`, `"abc123"`), not JSON blobs. |
| **Performance is not compromised** | No unnecessary copies, no extra serialization hops. Direct Kafka → Pydantic → Business logic. |

---

## What Gets Removed

### 1. `Channel` ABC and `Transport` ABC

```python
# REMOVED — tradingcz/transport/protocol.py
class Channel(ABC): ...
class Transport(ABC): ...
class Message: ...
```

**Why:** There is only one transport implementation (Kafka) and will never be another. The ABCs add 3 files of indirection (`protocol.py`, abstract methods, docstrings explaining "transport-agnostic") without delivering value. Python's duck typing already enables mocking for tests.

**Replacement:** `KafkaChannel` and `KafkaTransport` become the direct API. If you need a mock for testing, mock `KafkaChannel` — no ABC needed.

### 2. `tradingcz/transport/protocol.py` (the file)

The entire file goes. The only surviving abstraction is in `tradingcz/serialization/protocol.py` (`Serializer`, `Deserializer`, `Codec`), which is pure data conversion with no transport knowledge.

### 3. Transport-agnostic language in docstrings

All mentions of "REST, gRPC, WebSockets" and "transport-agnostic" are removed. The SDK is explicitly Kafka-based. Docstrings say what IS, not what might hypothetically be.

### 4. JSON blob keys

`EventKey` and `MarketDataKey` Pydantic models are removed (or repurposed as header models). Keys become plain strings:

```python
# Before (removed):
key = '{"source":"ingestion","broker":"alpaca","symbol":"AAPL","ts":"..."}'

# After:
key = "AAPL"
headers = {"source": "ingestion", "broker": "alpaca", "message_type": "trade", "schema_version": "1.0"}
```

### 5. `tradingcz/model/kafka_key.py`

Renamed to `tradingcz/model/message_headers.py` — models that were previously used as Kafka keys become header schemas.

---

## What Gets Simplified

### 1. Bootstrap: from ~40 lines to ~3 lines

**Before (current — every service copies this):**
```python
from tradingcz.config import KafkaSettings
from tradingcz.transport.kafka import TopicRegistry
from tradingcz.transport import KafkaTransport, TypedConsumer, TypedProducer, RequestReplyClient
from tradingcz.model.events import DataError, DataReady, DataRequest
from tradingcz.serialization import JsonCodec
from tradingcz.serialization.protocol import Deserializer
from tradingcz.model.ingestion import Bar

# ~40 lines of wiring...
settings = AppSettings()
kafka = KafkaSettings(bootstrap_servers=settings.bootstrap_servers, consumer_group=f"strategy-{settings.strategy_id}")
transport = KafkaTransport(kafka)
topics = TopicRegistry(env=settings.environment)
events_channel = await transport.channel(topics.events.name)
# ... TypedConsumer, TypedProducer, RequestReplyClient, key_fn lambdas ...
# ... 20 more lines ...
```

**After (proposed):**
```python
from tradingcz.sdk import TradingApp

app = TradingApp(env="dev", service_id="my-strategy")
await app.start()

# Business logic goes here — no Kafka knowledge needed
bars = await app.data.request_historical(["AAPL", "TSLA"], days=14)
```

### 2. TypedProducer/Consumer: no more manual key_fn lambdas

**Before:**
```python
ready_producer = TypedProducer(
    channel=events_channel,
    serializer=JsonCodec(DataReady),
    key_fn=lambda e: TopicRegistry.event_key("data_ready", "ingestion", e.request_id),
)
```

**After:**
```python
# key_fn is derived automatically from the topic + model type
ready_producer = app.events.producer(DataReady)  # key="ingestion", headers auto-populated
await ready_producer.send(data_ready)
```

### 3. `KafkaChannel` gets headers natively

No `Message` dataclass. `send()` and `receive()` work with explicit parameters:

```python
class KafkaChannel:
    async def send(
        self,
        payload: bytes,
        *,
        key: str = "",
        headers: dict[str, str] | None = None,
    ) -> None: ...

    async def receive(self) -> AsyncIterator[KafkaMessage]: ...
```

`KafkaMessage` is a lightweight wrapper that exposes what Kafka actually provides:
```python
@dataclass(frozen=True, slots=True)
class KafkaMessage:
    payload: bytes
    key: str
    headers: dict[str, str]
    offset: int          # Kafka-native, not pretending to be generic
    partition: int       # Kafka-native, not pretending to be generic
    topic: str           # Kafka-native, not pretending to be generic
```

This is honest: it's a Kafka message, named as such. No pretense of being "transport-agnostic."

### 4. `TopicRegistry` — simpler, with `key_fn` and `headers_fn` built in

```python
class TopicRegistry:
    def __init__(self, env: str = "dev") -> None:
        self.events = TopicConfig(name=f"{env}-event", partitions=1)
        self.market_data = TopicConfig(name=f"{env}-market-data", partitions=5)
        self.signals = TopicConfig(name=f"{env}-raw-signal", partitions=1)

    # Factory methods that return pre-configured functions — no lambdas needed
    def market_data_key(self, symbol: str) -> str:
        """Return the partition key for a market-data message."""
        return symbol  # plain string, not JSON

    def market_data_headers(self, *, source: str, broker: str, message_type: str) -> dict[str, str]:
        """Return standard headers for a market-data message."""
        return {
            "source": source,
            "broker": broker,
            "message_type": message_type,
            "schema_version": SCHEMA_VERSION,
        }
```

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────┐
│  BUSINESS LAYER  (NEW — what 90% of users touch)        │
│                                                         │
│  TradingApp    — one-stop setup + lifecycle              │
│  DataClient    — request_bars(), stream_quotes(), etc.  │
│  SignalClient  — publish(trading_signal)                │
│  EventClient   — request(), on_event(), etc.            │
│                                                         │
│  Usage: from tradingcz.sdk import TradingApp            │
│         app = TradingApp(env="dev", service_id="x")     │
│         await app.data.request_historical(["AAPL"])     │
├─────────────────────────────────────────────────────────┤
│  TYPED LAYER  (for power users & internal use)          │
│                                                         │
│  TypedProducer[T]    — send typed values                │
│  TypedConsumer[T]    — consume typed values             │
│  RequestReplyClient[Req, Resp]  — async req/reply       │
│                                                         │
│  These work directly with KafkaChannel (no ABC needed)  │
├─────────────────────────────────────────────────────────┤
│  KAFKA LAYER  (concrete, no abstraction)                │
│                                                         │
│  KafkaChannel       — one topic, send/receive           │
│  KafkaTransport     — channel factory + shared producer │
│  KafkaMessage       — honest wrapper around Kafka msg   │
│  TopicRegistry      — topic naming + config             │
│  KafkaSettings      — Pydantic settings                 │
├─────────────────────────────────────────────────────────┤
│  SERIALIZATION LAYER  (abstract, pure data)             │
│                                                         │
│  Serializer[T] / Deserializer[T] / Codec[T]  (ABCs)    │
│  JsonCodec[T]      — Pydantic ↔ JSON bytes             │
├─────────────────────────────────────────────────────────┤
│  MODEL LAYER  (pure Pydantic, no I/O)                   │
│                                                         │
│  tradingcz.model.ingestion   — Bar, Trade, Quote, etc.  │
│  tradingcz.model.events      — DataRequest, DataReady   │
│  tradingcz.model.signal      — TradingSignal, SignalKey │
│  tradingcz.model.executor    — ExecutionRequestEvent    │
│  tradingcz.model.message_headers  — standard header models │
├─────────────────────────────────────────────────────────┤
│  CONFIG LAYER                                            │
│                                                         │
│  KafkaSettings   — bootstrap, consumer_group, overrides │
│  AppSettings     — (optional) batteries-included setup  │
└─────────────────────────────────────────────────────────┘
```

### Key architectural decisions:

1. **No `Channel`/`Transport` ABCs.** `KafkaChannel` and `KafkaTransport` are the API. Test with mocks.

2. **Business layer is NEW.** It wraps the typed layer to provide operations named in business terms: `request_historical()`, `stream_quotes()`, `publish_signal()`.

3. **Typed layer stays.** `TypedProducer[T]`, `TypedConsumer[T]`, `RequestReplyClient` are proven abstractions. They now depend directly on `KafkaChannel` (concrete), not `Channel` (abstract).

4. **Serialization ABCs stay.** `Serializer`/`Deserializer`/`Codec` are pure data conversion. No transport dependency. Genuinely useful for future non-JSON formats (Avro, Protobuf).

5. **Models stay pure.** No changes to `tradingcz.model.*` except renaming `kafka_key.py` → `message_headers.py`.

6. **`KafkaMessage` is honest.** Named `KafkaMessage`, not `Message`. Carries Kafka-specific fields because it IS Kafka-specific. No pretense.

---

## Public API — The "Business Layer"

### `TradingApp` — One-stop setup

```python
"""The single entry point for SDK consumers.

Usage:
    from tradingcz.sdk import TradingApp

    app = TradingApp(env="dev", service_id="my-strategy")
    await app.start()

    # Use business-level APIs:
    bars = await app.data.request_historical(["AAPL"])
    async for quote in app.data.stream_quotes(["AAPL"]):
        ...

    await app.close()
"""

from dataclasses import dataclass
from tradingcz.config import KafkaSettings
from tradingcz.transport.kafka import KafkaTransport, TopicRegistry

@dataclass
class TradingApp:
    """Batteries-included SDK entry point.

    Creates transport, channels, producers, consumers, and business-level
    clients.  The user does NOT need to know about Kafka topics, partitions,
    serializers, or key functions.
    """

    env: str = "dev"
    service_id: str = "sdk-app"
    bootstrap_servers: str = "localhost:9092"

    # --- created by start() ---
    _transport: KafkaTransport | None = None
    _topics: TopicRegistry | None = None
    data: "DataClient | None" = None
    signals: "SignalClient | None" = None
    events: "EventClient | None" = None

    async def start(self) -> None:
        """Initialize transport and all business clients."""
        settings = KafkaSettings(
            bootstrap_servers=self.bootstrap_servers,
            consumer_group=self.service_id,
        )
        self._transport = KafkaTransport(settings)
        self._topics = TopicRegistry(env=self.env)

        # Create business-level clients
        self.data = DataClient(
            transport=self._transport,
            topics=self._topics,
            service_id=self.service_id,
        )
        self.signals = SignalClient(
            transport=self._transport,
            topics=self._topics,
        )
        self.events = EventClient(
            transport=self._transport,
            topics=self._topics,
            service_id=self.service_id,
        )

    async def close(self) -> None:
        """Graceful shutdown."""
        if self._transport:
            await self._transport.close()
```

### `DataClient` — Request market data

```python
"""Business-level API for requesting and consuming market data.

Users think in terms of "I need 14 days of AAPL bars" or "stream me TSLA quotes."
They do NOT think about topics, channels, serializers, or key functions.
"""

class DataClient:
    """High-level market data operations."""

    def __init__(self, transport: KafkaTransport, topics: TopicRegistry, service_id: str) -> None: ...

    async def request_historical(
        self,
        symbols: list[str],
        *,
        days: int = 14,
        timeframe: str = "1d",
        broker: str = "alpaca",
        timeout: float = 30.0,
    ) -> dict[str, list[Bar]]:
        """Request historical daily bars for *symbols*.

        Returns a dict mapping symbol → list of Bar, sorted by timestamp.

        Under the hood:
          1. Sends DataRequest(type="historic", ...) via RequestReplyClient
          2. Waits for DataReady response
          3. Consumes Bar messages from the ephemeral data channel
          4. Returns parsed results

        The caller writes ZERO lines of Kafka code.
        """
        ...

    async def stream_quotes(
        self,
        symbols: list[str],
        *,
        broker: str = "alpaca",
        timeout: float = 30.0,
    ) -> AsyncIterator[StreamQuote]:
        """Stream live quotes for *symbols*.

        Yields StreamQuote objects as they arrive. The caller controls
        when to stop by breaking out of the async for loop.

        Under the hood:
          1. Sends DataRequest(type="stream", stream_type="quotes", ...)
          2. Waits for DataReady response
          3. Subscribes to the market-data channel
          4. Yields parsed StreamQuote objects

        The caller writes ZERO lines of Kafka code.
        """
        ...

    async def stream_trades(
        self, symbols: list[str], *, broker: str = "alpoca", timeout: float = 30.0
    ) -> AsyncIterator[Trade]:
        """Stream live trades for *symbols*. Same pattern as stream_quotes()."""
        ...
```

### `SignalClient` — Publish trading signals

```python
class SignalClient:
    """Publish trading signals to the signals topic."""

    async def publish(self, signal: TradingSignal, *, tracking_id: str) -> None:
        """Publish a trading signal.

        The signal is serialized as a SignalEnvelope and sent to the
        signals topic.  Key = symbol, headers = {strategy_id, tracking_id, ...}.

        The caller writes ZERO lines of Kafka code.
        """
        ...
```

### `EventClient` — Request/reply on events topic

```python
class EventClient:
    """Send requests and await responses on the events topic."""

    async def request(self, req: DataRequest, *, timeout: float = 30.0) -> DataReady | DataError:
        """Send a DataRequest and wait for DataReady or DataError.

        Uses RequestReplyClient internally. Correlation by request_id.

        The caller writes ZERO lines of Kafka code.
        """
        ...

    def producer(self, model_type: type[T]) -> TypedProducer[T]:
        """Get a pre-configured TypedProducer for the events topic.

        Power-user escape hatch: use this if you need to send custom
        event types not covered by the high-level API.
        """
        ...
```

---

## What Stays the Same

| Component | Status | Reason |
|-----------|--------|--------|
| `JsonCodec[T]` | Unchanged | Perfect as-is. |
| `Serializer/Deserializer/Codec` ABCs | Unchanged | Pure data conversion. Useful when adding Avro/Protobuf later. |
| `TypedProducer[T]` / `TypedConsumer[T]` | Simplified | Drop `Channel` dependency, use `KafkaChannel` directly. Add `headers_fn`. |
| `RequestReplyClient[Req, Resp]` | Simplified | Drop `Channel` dependency. Add `headers_fn`. |
| `KafkaSettings` | Unchanged | Perfect as-is. |
| `TopicRegistry` | Simplified | Add `key_fn`/`headers_fn` factories. Remove JSON key models. |
| `tradingcz.model.*` | Minor rename | `kafka_key.py` → `message_headers.py`. |
| `tradingcz.indicators` | Unchanged | Pure functions. No transport dependency. |

---

## File Structure After Refactor

```
tradingcz/
├── __init__.py              # SCHEMA_VERSION constant
├── py.typed
│
├── sdk/                     # NEW — business layer
│   ├── __init__.py          # exports: TradingApp
│   ├── app.py               # TradingApp (one-stop setup)
│   ├── data.py              # DataClient
│   ├── signals.py           # SignalClient
│   └── events.py            # EventClient
│
├── transport/               # SIMPLIFIED — Kafka-concrete, no ABCs
│   ├── __init__.py          # exports: KafkaChannel, KafkaTransport, ...
│   ├── kafka_channel.py     # KafkaChannel + KafkaTransport
│   ├── kafka_message.py     # KafkaMessage (honest Kafka wrapper)
│   ├── typed.py             # TypedProducer, TypedConsumer
│   ├── request_reply.py     # RequestReplyClient
│   ├── topics.py            # TopicRegistry, TopicConfig
│   └── hash.py              # Murmur2 + partition_for() utility
│
├── serialization/           # UNCHANGED
│   ├── __init__.py
│   ├── protocol.py          # Serializer, Deserializer, Codec ABCs
│   └── json_codec.py        # JsonCodec[T]
│
├── config/                  # UNCHANGED
│   ├── __init__.py
│   └── settings.py          # KafkaSettings, LoggingSettings
│
├── model/                   # MINOR CHANGES
│   ├── __init__.py
│   ├── enum/                # Unchanged
│   ├── ingestion/           # Unchanged + add StreamQuote
│   ├── executor/            # Populated __init__.py
│   ├── events.py            # Unchanged
│   ├── signal.py            # Unchanged (remove build_signal → moved to serialization)
│   └── message_headers.py   # RENAMED from kafka_key.py — header models, not key models
│
├── indicators/              # UNCHANGED
│   ├── __init__.py
│   └── atr.py
│
└── errors.py                # NEW — shared error types
```

### Files removed:

| Removed File | Reason |
|-------------|--------|
| `tradingcz/transport/protocol.py` | `Channel`/`Transport` ABCs no longer needed |
| `tradingcz/transport/stream.py` | Merged into `transport/typed.py` |
| `tradingcz/model/kafka_key.py` | Renamed to `message_headers.py` |

### Files added:

| New File | Purpose |
|----------|---------|
| `tradingcz/sdk/app.py` | `TradingApp` — one-stop setup |
| `tradingcz/sdk/data.py` | `DataClient` — request historical, stream |
| `tradingcz/sdk/signals.py` | `SignalClient` — publish signals |
| `tradingcz/sdk/events.py` | `EventClient` — request/reply on events |
| `tradingcz/transport/kafka_message.py` | `KafkaMessage` — honest Kafka wrapper |
| `tradingcz/transport/hash.py` | Murmur2 + `partition_for()` |
| `tradingcz/errors.py` | Shared error types |

---

## Performance Considerations

The simplification does NOT introduce overhead:

1. **No extra serialization hops.** `TradingApp.data.request_historical()` uses the same `JsonCodec` → `KafkaChannel.send()` path as the current manual code. It's just packaged.

2. **No extra copies.** `KafkaMessage` is a thin dataclass wrapping librdkafka's message object. Headers are decoded lazily.

3. **Same async patterns.** `TypedProducer` and `RequestReplyClient` use the same `AIOProducer`/`AIOConsumer` under the hood.

4. **Business layer is zero-cost.** `DataClient.stream_quotes()` is just a generator wrapper around `TypedConsumer`. No buffering, no transformation.

5. **Headers are encoded once.** When using `TradingApp`, headers are pre-computed at client creation time, not per-message. The `headers_fn` pattern is only used for dynamic headers (e.g., per-message `trace_id`).

---

## Migration Path

### Phase 1: Add the new code (non-breaking)

1. Add `tradingcz/transport/kafka_message.py` — `KafkaMessage` dataclass
2. Add `tradingcz/transport/typed.py` — `TypedProducer`/`TypedConsumer` refactored to use `KafkaChannel` directly
3. Add `tradingcz/transport/hash.py` — Murmur2 utility
4. Add `tradingcz/errors.py` — shared error types
5. Add `tradingcz/sdk/` — business layer (`TradingApp`, `DataClient`, etc.)
6. Add `tradingcz/model/message_headers.py` — renamed from `kafka_key.py`
7. Add headers support to `KafkaChannel.send()` and `KafkaChannel.receive()` (additive, non-breaking)
8. Deprecate `tradingcz/transport/protocol.py` — add `DeprecationWarning` on import
9. Deprecate `tradingcz/model/kafka_key.py` — re-export from `message_headers.py` with warning

### Phase 2: Migrate consumers (one service at a time)

1. **simple-strategy** — easiest migration (smallest codebase):
   ```python
   # Before (~40 lines):
   settings = StrategySettings()
   kafka = KafkaSettings(...)
   transport = KafkaTransport(kafka)
   topics = TopicRegistry(env=settings.environment)
   events_channel = await transport.channel(topics.events.name)
   # ... 20 more lines ...

   # After (~4 lines):
   app = TradingApp(env="dev", service_id=settings.strategy_id)
   await app.start()
   bars = await app.data.request_historical(settings.symbols, days=settings.lookback_days)
   ```

2. **ingestion** — slightly more complex (produces data, doesn't consume it):
   ```python
   app = TradingApp(env=settings.environment, service_id="ingestion")
   await app.start()
   # Use TypedProducer directly for control-plane responses
   ready_producer = app.events.producer(DataReady)
   ```

3. **executor** — needs version bump first (v0.0.10 → latest), then adopt `TradingApp`.

### Phase 3: Remove deprecated code

1. Remove `tradingcz/transport/protocol.py`
2. Remove `tradingcz/model/kafka_key.py`
3. Update all imports

---

## Before/After Comparison

### Scenario: A new developer writes a strategy that needs historical bars and live quotes

**Before (current SDK):**
```python
import asyncio
from datetime import UTC, datetime, timedelta
from tradingcz.config import KafkaSettings
from tradingcz.transport.kafka import TopicRegistry
from tradingcz.transport import KafkaTransport, RequestReplyClient
from tradingcz.model.events import DataError, DataReady, DataRequest
from tradingcz.model.ingestion import Bar, StreamQuote
from tradingcz.serialization import JsonCodec
from tradingcz.serialization.protocol import Deserializer

# Developer must understand:
# - KafkaSettings, bootstrap_servers, consumer_group
# - KafkaTransport, channels, topic naming
# - TypedProducer, TypedConsumer, serializers
# - RequestReplyClient, key_fn, request_id_of, response_id_of
# - TopicRegistry, event_key, market_data_key
# - The DataRequest/DataReady/DataError protocol
# - Ephemeral channel lifecycle
# - Bar/StreamQuote parsing from raw bytes

class _DataResponseDeserializer(Deserializer):
    def deserialize(self, payload: bytes):
        from tradingcz.model.events import parse_event
        event = parse_event(payload)
        if isinstance(event, (DataReady, DataError)):
            return event
        raise ValueError(...)
    def content_type(self): return "application/json"

async def run():
    settings = StrategySettings()
    kafka = KafkaSettings(
        bootstrap_servers=settings.bootstrap_servers,
        consumer_group=f"strategy-{settings.strategy_id}",
    )
    transport = KafkaTransport(kafka)
    topics = TopicRegistry(env=settings.environment)
    events_channel = await transport.channel(topics.events.name)

    async with RequestReplyClient[DataRequest, DataReady|DataError](
        channel=events_channel,
        request_serializer=JsonCodec(DataRequest),
        response_deserializer=_DataResponseDeserializer(),
        request_id_of=lambda r: r.request_id,
        response_id_of=lambda r: r.request_id,
        key_fn=lambda r: TopicRegistry.event_key(
            "data_request", f"strategy-{settings.strategy_id}", r.request_id,
        ),
        timeout=30.0,
    ) as client:
        # Phase 1: historical bars (~30 more lines of channel/receive/parse)
        request = DataRequest(type="historic", symbols=["AAPL"], ...)
        response = await client.request(request)
        data_channel = await transport.channel(response.data_topic)
        bars_by_symbol = {}
        async for msg in data_channel.receive():
            bar = Bar.model_validate_json(msg.payload)
            ...

        # Phase 2: stream quotes (~30 more lines)
        ...
```

**After (proposed SDK):**
```python
import asyncio
from tradingcz.sdk import TradingApp

# Developer only needs to understand:
# - TradingApp (one import, one setup call)
# - DataClient methods named in business terms
# - Bar, StreamQuote, TradingSignal (domain models they already know)

async def run():
    settings = StrategySettings()
    app = TradingApp(env="dev", service_id=settings.strategy_id)
    await app.start()

    # Phase 1: historical bars — one line, typed return
    bars_by_symbol = await app.data.request_historical(
        ["AAPL", "TSLA"], days=settings.lookback_days,
    )

    # Phase 2: stream quotes — async for loop, typed values
    async for quote in app.data.stream_quotes(["AAPL", "TSLA"]):
        # quote is a StreamQuote — already parsed, typed
        if quote.symbol in emitted:
            continue
        # ... business logic ...

    await app.close()
```

**Lines of code:** ~65 → ~20
**Kafka concepts exposed:** ~12 → 0
**Import statements:** ~10 → 1

---

## Summary

| Design Decision | Rationale |
|----------------|-----------|
| Remove `Channel`/`Transport` ABCs | Only one transport. ABCs are indirection without value. Mock concrete classes for tests. |
| Keep `Serializer`/`Deserializer`/`Codec` ABCs | Pure data conversion. Transport-independent. Genuinely useful. |
| Add `TradingApp` business layer | Users should NOT think about Kafka. They think "I need bars" or "stream me quotes." |
| `KafkaMessage` is honest about being Kafka | No pretense. Carries `offset`, `partition`, `topic` because it IS a Kafka message. |
| Headers first-class, keys plain strings | Metadata in headers, routing in keys. Clean separation. |
| `build_signal()` moved to serialization | Model layer stays pure. Serialization handles bytes. |
| `TopicRegistry` provides factories | No more lambda boilerplate for `key_fn`/`headers_fn`. |
| Keep `TypedProducer`/`TypedConsumer` public | Power-user escape hatch for custom message types/flows. |
