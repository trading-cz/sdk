# SDK Improvements & Kafka Architecture Analysis

> **Date:** 2026-05-28
> **Scope:** `trading-sdk` repository + cross-service Kafka usage review
> **Repos:** `sdk`, `ingestion`, `simple-strategy`, `executor`

---

## Table of Contents

1. [(a) Validate Overall Idea](#a-validate-overall-idea)
2. [(b) Evaluate Abstraction & Layering](#b-evaluate-abstraction--layering)
3. [(c) Improvements & Weaknesses](#c-improvements--weaknesses)
4. [(d) What Is Missing](#d-what-is-missing)
5. [(e) Transport Layer Design & Reusability](#e-transport-layer-design--reusability)
6. [(f) Kafka Topic & Usage Deep-Dive](#f-kafka-topic--usage-deep-dive)
   - [f.1 Architecture Overview](#f1-architecture-overview)
   - [f.2 Producer Checks](#f2-producer-checks)
   - [f.3 Consumer Checks](#f3-consumer-checks)
   - [f.4 Operational Checks](#f4-operational-checks)
   - [f.5 Corrected Code Snippets](#f5-corrected-code-snippets)
7. [Priority Actions Summary](#priority-actions-summary)

---

## (a) Validate Overall Idea

### Finding A-1: Concept is sound ✅

The shared SDK correctly identifies the two things that MUST be shared across services:
1. **Wire-format models** — `Bar`, `Trade`, `DataRequest`, `TradingSignal`, etc. (the contract between services).
2. **Transport boilerplate** — Kafka setup, producer/consumer creation, serialization, request/reply correlation.

Without this SDK, each of the 5+ services would duplicate models and Kafka wiring.

**What's working well:**
- `tradingcz.model` namespace — clean Pydantic models with `frozen=True`, no vendor dependencies, no I/O.
- `JsonCodec[T]` — simple, correct, reusable.
- `TypedProducer[T]` / `TypedConsumer[T]` — right level of abstraction.
- `RequestReplyClient[Req, Resp]` — clean generic async pattern.

---

### Finding A-2: Version Fragmentation 🔴 HIGH

| Service | SDK Version | Source |
|---------|------------|--------|
| ingestion | v0.0.15 | `git+https://github.com/trading-cz/sdk@v0.0.15` |
| simple-strategy | v0.0.15 | `git+https://github.com/trading-cz/sdk@v0.0.15` |
| executor | v0.0.10 | Static wheel from GitHub Releases |

The executor has its own local fork of SDK-like models under `tradingcz.executor.sdk.*`. The shared SDK's `tradingcz.model.executor.*` models directly mirror those in the executor but are not wired together.

**Recommended Solution:**
1. Bump the executor's SDK dependency to v0.0.15 (or latest).
2. Replace `from tradingcz.executor.sdk.events.execution_request_event import ExecutionRequestEvent` with `from tradingcz.model.executor.events import ExecutionRequestEvent` from the shared SDK.
3. Delete the executor's local `tradingcz/executor/sdk/` directory once migration is complete.
4. Add a CI check that verifies all repos use the same SDK version.

---

## (b) Evaluate Abstraction & Layering

### Current Layer Stack

```
Layer 2:  TypedProducer[T] / TypedConsumer[T] / RequestReplyClient[Req,Resp]
           ↑ typed domain models
Layer 1:  Serializer[T] / Deserializer[T] / Codec[T]  (JsonCodec)
           ↑ bytes
Layer 0:  Channel / Transport  (protocol ABCs)
           ↑ raw Kafka I/O
         ─────────────────────
         KafkaChannel / KafkaTransport  (concrete)
```

This is clean, minimal, and well-separated.

---

### Finding B-1: `Message` dataclass is too narrow 🟡 MEDIUM

**Problem:** `Message` only has `payload: bytes` and `key: str`. Kafka messages also carry headers, timestamps, partition info, and offsets.

```python
# Current — too narrow
@dataclass(frozen=True, slots=True)
class Message:
    payload: bytes
    key: str = ""
```

**Recommended Solution:**
```python
# Add headers and offset metadata
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Message:
    payload: bytes
    key: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    offset: int = -1
    partition: int = -1
    topic: str = ""
```

---

### Finding B-2: `Channel.receive()` has no backpressure or lifecycle hooks 🟡 MEDIUM

**Problem:** No way to acknowledge/commit offsets, pause/resume consumption, or batch. For at-least-once processing, offset commits are essential.

**Recommended Solution:**
```python
@dataclass(frozen=True, slots=True)
class ReceivedMessage(Message):
    ack: Callable[[], Awaitable[None]]   # commit offset
    nack: Callable[[], Awaitable[None]]  # retry / dead-letter

class Channel(ABC):
    @abstractmethod
    async def receive(self) -> AsyncIterator[ReceivedMessage]:
        ...
```

---

### Finding B-3: `KafkaTransport` mixes topic admin with transport 🟡 MEDIUM

**Problem:** `KafkaTransport._ensure_topic()` auto-creates topics via Admin API. This is an infrastructure concern, not a transport concern. It requires `AdminClient` permissions at runtime and masks configuration drift.

**Recommended Solution:**
1. Extract topic creation into a separate `KafkaTopicAdmin` class:
```python
# tradingcz/transport/kafka/admin.py (new file)
class KafkaTopicAdmin:
    def __init__(self, bootstrap_servers: str) -> None: ...
    async def ensure_topic(self, name: str, *, num_partitions: int = 5,
                           replication_factor: int = 2, retention_ms: int = 432000000,
                           cleanup_policy: str = "delete") -> None: ...
    async def delete_topic(self, name: str) -> None: ...
    async def list_topics(self) -> dict[str, Any]: ...
    async def alter_partitions(self, name: str, num_partitions: int) -> None: ...
```
2. `KafkaTransport` should raise `TopicNotFoundError` if a topic doesn't exist (fail fast, don't auto-create).
3. Use `KafkaTopicAdmin` in dev/test scripts and CI, not in production runtime.

---

### Finding B-4: Premature abstraction — mention of REST/gRPC/WS 🟢 LOW

**Problem:** Docstrings mention "REST, gRPC, WebSockets" as alternative transports, but there's no realistic plan for any of them. This creates false expectations.

**Recommended Solution:**
- Keep the ABCs (they're valuable for testability), but update docstrings:
> *"The `Channel` and `Transport` ABCs exist to enable testing with mock channels and to enforce a clean separation between transport logic and domain logic. There is no current plan to support transports other than Kafka."*

---

## (c) Improvements & Weaknesses

### ✅ Good Design Choices (Keep)

| Choice | Reason |
|--------|--------|
| `TopicRegistry` as single source of truth | Topic names computed centrally, not scattered |
| `parse_event()` discriminated union | Clean `DataRequest \| DataReady \| DataError` parsing |
| Frozen Pydantic models everywhere | No mutable shared state |
| `KafkaSettings` with `producer_overrides`/`consumer_overrides` | Tune librdkafka from ConfigMap without code changes |

---

### Finding C-1: `build_signal()` leaks transport concern into model layer 🔴 HIGH

**Problem:** `tradingcz/model/signal.py` contains `build_signal()` which returns `bytes` — a serialization concern. It also constructs `SignalEnvelope` (key+value split), which is Kafka-specific.

**Recommended Solution:**
1. Move `build_signal()` and `SignalEnvelope` to a new module: `tradingcz/serialization/signal_codec.py`
2. Keep `TradingSignal`, `SignalKey`, `SignalValue`, `SignalMetadata` as pure Pydantic models in `tradingcz/model/signal.py`.
3. The new `signal_codec.py` imports from `model/signal.py` and from `serialization/json_codec.py`.

```python
# tradingcz/serialization/signal_codec.py (new file)
"""Signal serialization — encode TradingSignal to Kafka-ready envelope bytes."""
import uuid
from datetime import datetime

from tradingcz.model.signal import (
    TradingSignal, SignalKey, SignalValue, SignalMetadata, SignalEnvelope
)

class SignalCodec:
    """Serialize/deserialize TradingSignal to/from Kafka envelope bytes."""

    @staticmethod
    def encode(signal: TradingSignal, tracking_id: str, timestamp_utc_ms: int) -> bytes:
        """Serialize a TradingSignal to Kafka-ready bytes."""
        envelope = SignalEnvelope(
            key=SignalKey(
                tracking_id=tracking_id,
                timestamp_utc_ms=timestamp_utc_ms,
                strategy_id=signal.strategy_id,
            ),
            value=SignalValue(
                symbol=signal.symbol,
                side=signal.side,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                valid_until_et=signal.valid_until_et,
                metadata=SignalMetadata(
                    open_price=signal.open_price,
                    atr_period=signal.atr_period,
                    atr_value=signal.atr_value,
                ),
            ),
        )
        return envelope.model_dump_json().encode()

    @staticmethod
    def decode(raw: bytes) -> SignalEnvelope:
        """Deserialize Kafka bytes back to a SignalEnvelope."""
        return SignalEnvelope.model_validate_json(raw)
```

---

### Finding C-2: `TopicRegistry` JSON key methods are not reusable as `key_fn` 🟡 MEDIUM

**Problem:** Every consumer manually wraps key methods in lambdas:
```python
# Repetitive boilerplate across ingestion AND simple-strategy
key_fn=lambda e: TopicRegistry.event_key("data_ready", "ingestion", e.request_id),
key_fn=lambda e: TopicRegistry.event_key("data_error", "ingestion", e.request_id),
key_fn=lambda r: TopicRegistry.event_key("data_request", f"strategy-{id}", r.request_id),
```

**Recommended Solution:**
Add factory methods to `TopicRegistry` that return pre-bound `Callable`:
```python
# tradingcz/transport/kafka/topics.py — add to TopicRegistry
from collections.abc import Callable
from typing import Protocol

class HasRequestId(Protocol):
    request_id: str

class HasSymbol(Protocol):
    symbol: str

class TopicRegistry:
    def event_key_fn(self, event_type: str, source: str) -> Callable[[HasRequestId], str]:
        """Return a key_fn for TypedProducer on the events topic."""
        def _key(event: HasRequestId) -> str:
            return self.event_key(event_type, source, event.request_id)
        return _key

    def market_data_key_fn(self, source: str, broker: str) -> Callable[[HasSymbol], str]:
        """Return a key_fn for TypedProducer on the market-data topic."""
        def _key(item: HasSymbol) -> str:
            return self.market_data_key(source, broker, item.symbol)
        return _key
```
Then usage simplifies to:
```python
ready_producer = TypedProducer(
    channel=events_channel,
    serializer=JsonCodec(DataReady),
    key_fn=topics.event_key_fn("data_ready", "ingestion"),  # clean!
)
```

---

### Finding C-3: `StreamQuote` used in production but absent from SDK source 🔴 HIGH

**Problem:** `simple-strategy` imports `StreamQuote` from `tradingcz.model.ingestion`, but no `StreamQuote` class exists in the SDK source tree. It is presumably in an older wheel or generated externally.

**Recommended Solution:**
1. Locate the actual source of `StreamQuote` (likely a generated model from an older SDK build or from the `trading-model` external package).
2. Add it to `tradingcz/model/ingestion/` in the SDK source:
```python
# tradingcz/model/ingestion/stream_quote.py (new file)
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class StreamQuote(BaseModel):
    """A streaming quote from a broker — wraps raw Quote with metadata."""
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    quote: Quote  # from tradingcz.model.ingestion.quote
```
3. Re-export in `tradingcz/model/ingestion/__init__.py`.

---

### Finding C-4: Empty `__init__.py` in executor model subpackages 🔴 HIGH

**Problem:** `tradingcz/model/executor/events/__init__.py` and `tradingcz/model/executor/orders/__init__.py` are empty. Models are not importable via the public API.

**Recommended Solution:**
Populate with re-exports matching the pattern used by `tradingcz/model/ingestion/__init__.py`:
```python
# tradingcz/model/executor/events/__init__.py
from tradingcz.model.executor.events.base_event import BaseEvent
from tradingcz.model.executor.events.execution_request_event import ExecutionRequestEvent
from tradingcz.model.executor.events.service_request_event import ServiceRequestEvent
from tradingcz.model.executor.events.single_order_request import SingleOrderRequest

__all__ = ["BaseEvent", "ExecutionRequestEvent", "ServiceRequestEvent", "SingleOrderRequest"]

# tradingcz/model/executor/orders/__init__.py
from tradingcz.model.executor.orders.broker_order_response import BrokerOrderResponse

__all__ = ["BrokerOrderResponse"]
```

---

### Finding C-5: Inconsistent docstring quality 🟢 LOW

**Problem:** `tradingcz/model/ingestion/__init__.py` says "Lightweight dataclasses (slots=True, frozen=True)" but models are Pydantic `BaseModel`, not Python `@dataclass`.

**Recommended Solution:**
Change the docstring to: *"Pydantic models (frozen=True) with no vendor dependencies."*

---

### Finding C-6: `RequestReplyClient` swallows deserialization errors silently 🟡 MEDIUM

**Problem:**
```python
except (ValueError, TypeError, LookupError):
    continue  # silently skip — no counter, no debug log
```
`LookupError` is never raised by Pydantic. Messages are lost with zero visibility.

**Recommended Solution:**
```python
# In RequestReplyClient._listen():
except (ValueError, TypeError):
    self._skipped_count += 1
    logger.debug(
        "Skipping non-response message on %s (total skipped=%d)",
        self._channel.name,
        self._skipped_count,
    )
    continue
```
Also expose `skipped_count` as a public property for monitoring:
```python
@property
def skipped_count(self) -> int:
    """Number of messages skipped because they didn't match the expected response type."""
    return self._skipped_count
```

---

## (d) What Is Missing

### Finding D-1: No shared error type hierarchy 🟡 MEDIUM

**Problem:** Each service defines its own exceptions. Consumers can't catch a shared base.

**Recommended Solution:**
```python
# tradingcz/errors.py (new file)
"""Shared error types for the trading SDK."""

class SdkError(Exception):
    """Base for all SDK-raised exceptions."""

class TransportError(SdkError):
    """Transport-level failure (connection, timeout, broker unreachable)."""

class ConnectionError(TransportError):
    """Cannot connect to the transport backend."""

class TimeoutError(TransportError):
    """Operation timed out at the transport level."""

class SerializationError(SdkError):
    """Serialization or deserialization failed."""

class ConfigurationError(SdkError):
    """Invalid SDK configuration."""

class TopicNotFoundError(TransportError):
    """The requested topic does not exist."""
```

---

### Finding D-2: No logging hooks 🟡 MEDIUM

**Problem:** Every service manually calls `logging.getLogger(__name__)`. There's no structured logging context (correlation IDs, trace IDs) in the SDK.

**Recommended Solution:**
```python
# tradingcz/logging.py (new file)
"""Logging utilities for SDK consumers."""
import logging
import contextvars

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)

def get_request_id() -> str:
    """Get the current request correlation ID."""
    return _request_id.get()

def set_request_id(rid: str) -> None:
    """Set the current request correlation ID."""
    _request_id.set(rid)

def setup_sdk_logging(level: str = "INFO") -> None:
    """Configure consistent log format for all SDK loggers."""
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s [%(levelname)-7s] %(name)s "
            "rid=%(request_id)s: %(message)s"
        ),
    )
```

---

### Finding D-3: No metrics/observability hooks 🟡 MEDIUM

**Problem:** No Prometheus counters, histograms, or OpenTelemetry spans in the transport layer.

**Recommended Solution:**
Add optional hooks to `Channel` — the SDK doesn't depend on `prometheus_client`, just provides callbacks:
```python
class Channel(ABC):
    # Optional callbacks — services wire these to their own metrics systems
    on_send: Callable[[Message], None] | None = None
    on_receive: Callable[[Message], None] | None = None
    on_error: Callable[[Exception], None] | None = None
```

Services wire them at startup:
```python
from prometheus_client import Counter

messages_sent = Counter("kafka_messages_sent_total", "...", ["topic"])
channel.on_send = lambda msg: messages_sent.labels(topic=channel.name).inc()
```

---

### Finding D-4: No consumer group coordination 🟡 MEDIUM

**Problem:** No rebalance listeners, no graceful offset commit, no consumer lag monitoring.

**Recommended Solution:**
Add a `ConsumerGroup` wrapper in a new file:
```python
# tradingcz/transport/kafka/consumer_group.py (new file)
"""Consumer group wrapper with rebalance handling and offset commit."""
import asyncio
import logging
from collections.abc import Callable
from confluent_kafka.aio import AIOConsumer
from confluent_kafka import TopicPartition

from tradingcz.config.settings import KafkaSettings

logger = logging.getLogger(__name__)

class ConsumerGroup:
    """Wraps AIOConsumer with rebalance callbacks and graceful shutdown."""

    def __init__(
        self,
        settings: KafkaSettings,
        topics: list[str],
        group_id: str,
        *,
        on_assign: Callable[[list[TopicPartition]], None] | None = None,
        on_revoke: Callable[[list[TopicPartition]], None] | None = None,
    ) -> None:
        config = settings.consumer_config(group_id=group_id)
        self._consumer = AIOConsumer(config)
        self._topics = topics
        self._on_assign = on_assign
        self._on_revoke = on_revoke

    async def start(self) -> None:
        """Subscribe to topics."""
        await self._consumer.subscribe(self._topics)

    async def poll(self, timeout: float = 1.0) -> Any:
        """Poll for a message."""
        return await self._consumer.poll(timeout)

    async def commit(self) -> None:
        """Commit current offsets synchronously."""
        await self._consumer.commit()

    async def close(self) -> None:
        """Graceful shutdown: commit offsets, close consumer."""
        try:
            await self._consumer.commit()
        except Exception:
            logger.warning("Failed to commit offsets during shutdown", exc_info=True)
        await self._consumer.close()

    @property
    def consumer(self) -> AIOConsumer:
        """Access the underlying AIOConsumer for advanced use."""
        return self._consumer
```

---

### Finding D-5: No batching support 🟢 LOW

**Problem:** `TypedProducer.send()` is single-message only. For high-throughput streaming data, this is inefficient.

**Recommended Solution:**
```python
class TypedProducer[T]:
    async def send_batch(self, values: list[T]) -> None:
        """Serialize and publish a batch. Override for bulk send."""
        for v in values:
            await self.send(v)
```
The default is sequential; Kafka-specific overrides can use batch produce APIs in the future.

---

### Finding D-6: No schema versioning strategy 🟡 MEDIUM

**Problem:** `SignalKey` has `schema_version: str = "1.0"` but only for signals. No central constant, no version in `Bar`/`Trade`/`DataRequest`.

**Recommended Solution:**
1. Define a package-level constant:
```python
# tradingcz/__init__.py — add:
SCHEMA_VERSION = "1.0"
```
2. Embed it as a **Kafka header** on every message (see Finding F-1).

---

### Finding D-7: No `KeyStrategy` protocol 🟢 LOW

**Problem:** `key_fn: Callable[[T], str]` is anonymous and untyped — unclear what it should return.

**Recommended Solution:**
```python
# tradingcz/transport/protocol.py — add:
class KeyStrategy[T](ABC):
    """Named, documented strategy for computing Kafka message keys."""
    @abstractmethod
    def key_for(self, value: T) -> str: ...
```
This lets consumers pass named, discoverable strategies:
```python
class SymbolPartitionKey(KeyStrategy[Bar]):
    """Route bars by symbol for per-symbol ordering."""
    def key_for(self, bar: Bar) -> str:
        return bar.symbol
```

---

## (e) Transport Layer Design & Reusability

### Finding E-1: Single event topic — evaluates correctly ℹ️ INFO

The `{env}-event` topic (1 partition) is correct for the current low-volume use case (hundreds/day of `DataRequest`/`DataReady`/`DataError` messages).

**Recommended Solution:** No change needed. Revisit if volume exceeds a few hundred messages/second.

---

### Finding E-2: Request/reply race condition on shared topic 🟡 MEDIUM

**Problem:** `RequestReplyClient` produces and consumes on the same topic. If a `DataReady` is produced before the consumer's `subscribe()` completes (group coordinator lag), the response is missed. The timeout will fire eventually but adds latency.

**Recommended Solution:**
Add an optional `reply_channel` parameter to `RequestReplyClient` for future scenarios:
```python
class RequestReplyClient[Req, Resp]:
    def __init__(
        self,
        channel: Channel,          # request channel
        *,
        reply_channel: Channel | None = None,  # NEW: separate reply channel
        ...
    ) -> None:
```

---

### Finding E-3: Unused topic configs in `TopicRegistry` 🟢 LOW

**Problem:** `execution_requests`, `execution_responses`, and `positions` topics are defined but have zero consumers.

**Recommended Solution:** Comment them out with a TODO:
```python
# FUTURE — uncomment when executor adopts shared SDK
# self.execution_requests = TopicConfig(name=f"{env}-execution-request", partitions=1)
# self.execution_responses = TopicConfig(name=f"{env}-execution-response", partitions=1)
# self.positions = TopicConfig(name=f"{env}-position-events", partitions=1)
```

---

### Finding E-4: Ephemeral topics never deleted 🟡 MEDIUM

**Problem:** `{env}-market-data-historical-{request_id}` topics accumulate. The default retention of 5 days (from `TopicConfig`) means stale historical data lingers.

**Recommended Solution:**
1. Set explicit short retention on ephemeral topics:
```python
# In KafkaTransport.channel(), when creating ephemeral topics:
if "-historical-" in name:
    retention_ms = 3_600_000  # 1 hour for ephemeral historical data
```
2. Add a cleanup method:
```python
class KafkaTopicAdmin:
    async def cleanup_historical_topics(self, env: str = "dev") -> int:
        """Delete ephemeral historical topics for *env*. Returns count deleted."""
        topics = await self.list_topics()
        prefix = f"{env}-market-data-historical-"
        deleted = 0
        for name in topics:
            if name.startswith(prefix):
                await self.delete_topic(name)
                deleted += 1
        return deleted
```

---

### Finding E-5: `kafka_key.py` module name leaks transport into model 🟢 LOW

**Problem:** `tradingcz.model.kafka_key` has "Kafka" in the module name, but it lives in the model layer which should be transport-agnostic.

**Recommended Solution:**
Rename `tradingcz/model/kafka_key.py` → `tradingcz/model/message_key.py`.

---

## (f) Kafka Topic & Usage Deep-Dive

### f.1 Architecture Overview

The system uses three Kafka usage patterns:

#### Pattern 1: Event Topic (Control Plane)

```
Topic:      {env}-event  (1 partition)
Volume:     Hundreds/day
Key:        EventKey JSON (contains metadata — SHOULD BE in headers)
Value:      DataRequest | DataReady | DataError (JSON)
Headers:    [NOT USED]
```

#### Pattern 2: Streaming/Market Data Topic

```
Topic:      {env}-market-data  (5 partitions)
Volume:     Millions/day (quotes, trades, bars)
Key:        MarketDataKey JSON (contains metadata — SHOULD BE in headers)
Value:      Bar | Trade | Quote | StreamQuote (JSON)
Headers:    [NOT USED]
```

#### Pattern 3: Ephemeral Historical Topics

```
Topic:      {env}-market-data-historical-{request_id}  (5 partitions, auto-created)
Volume:     Burst (one request = N bars)
Key:        MarketDataKey JSON (same as Pattern 2)
Value:      Bar (JSON)
Headers:    [NOT USED]
```

---

### f.2 Producer Checks

#### Finding F-1: No Kafka headers — metadata incorrectly in JSON keys 🔴 HIGH (CRITICAL)

**Problem:** All message metadata (`event_type`, `source`, `broker`, `schema_version`, `trace_id`, `ts`) is stuffed into the JSON message key. This is an anti-pattern because:

1. **Keys are for partition routing, not metadata.** A key should be a simple value (symbol, request_id) that determines which partition the message lands on.
2. **Reading metadata requires deserializing the JSON key** — expensive for consumers that only need to filter by message type.
3. **JSON keys bloat partition hashing** — the full JSON string is hashed, but only the symbol portion determines the desired partition.

**Current (wrong) pattern:**
```
Key:    '{"source":"ingestion","broker":"alpaca","symbol":"AAPL","ts":"2026-05-28T..."}'
Value:  {"symbol":"AAPL","price":150.25,"timestamp":"..."}
Headers: (none)
```

**Correct pattern:**
```
Key:    "AAPL"                                 ← plain symbol, for partitioning only
Value:  {"symbol":"AAPL","price":150.25,"..."}  ← domain payload
Headers:
  message_type: "trade"
  source: "ingestion"
  broker: "alpaca"
  schema_version: "1.0"
  trace_id: "abc123-def456"
  ts: "2026-05-28T12:00:00Z"
```

**Recommended Solution — Implementation Plan:**

**Step 1 — Update `Message` dataclass and `Channel` ABC to support headers:**
```python
# tradingcz/transport/protocol.py
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Message:
    payload: bytes
    key: str = ""
    headers: dict[str, str] = field(default_factory=dict)

class Channel(ABC):
    @abstractmethod
    async def send(
        self, payload: bytes, *, key: str = "",
        headers: dict[str, str] | None = None,
    ) -> None: ...
```

**Step 2 — Update `KafkaChannel.send()` to pass headers to librdkafka:**
```python
# tradingcz/transport/kafka/channel.py
async def send(
    self, payload: bytes, *, key: str = "",
    headers: dict[str, str] | None = None,
) -> None:
    key_bytes = key.encode() if key else None
    header_list = (
        [(k, v.encode()) for k, v in headers.items()]
        if headers else None
    )
    delivery_future = await self._producer.produce(
        self._topic, value=payload, key=key_bytes, headers=header_list,
    )
    await delivery_future
```

**Step 3 — Update `KafkaChannel.receive()` to extract headers:**
```python
async def receive(self) -> AsyncIterator[Message]:
    # ... consumer setup ...
    while True:
        msg = await consumer.poll(self._settings.consumer_poll_timeout)
        if msg is None:
            continue
        if msg.error():
            logger.error("Kafka consumer error on %s: %s", self._topic, msg.error())
            continue
        key = msg.key().decode() if msg.key() else ""
        # Extract headers
        raw_headers = msg.headers() or []
        headers = {
            h[0]: h[1].decode() if isinstance(h[1], bytes) else str(h[1])
            for h in raw_headers
        }
        yield Message(
            payload=msg.value(),
            key=key,
            headers=headers,
            offset=msg.offset(),
            partition=msg.partition(),
            topic=msg.topic(),
        )
    # ...
```

**Step 4 — Update `TypedProducer` to accept `headers_fn`:**
```python
# tradingcz/transport/stream.py
class TypedProducer[T]:
    def __init__(
        self,
        channel: Channel,
        serializer: Serializer[T],
        *,
        key_fn: Callable[[T], str] | None = None,
        headers_fn: Callable[[T], dict[str, str]] | None = None,
    ) -> None:
        self._channel = channel
        self._serializer = serializer
        self._key_fn = key_fn or (lambda _: "")
        self._headers_fn = headers_fn

    async def send(self, value: T) -> None:
        payload = self._serializer.serialize(value)
        key = self._key_fn(value)
        headers = self._headers_fn(value) if self._headers_fn else None
        await self._channel.send(payload, key=key, headers=headers)
```

**Step 5 — Simplify keys to plain strings:**
```python
# Before:
key = TopicRegistry.market_data_key("ingestion", "alpaca", "AAPL")
# → '{"source":"ingestion","broker":"alpaca","symbol":"AAPL","ts":"..."}'

# After:
key = "AAPL"  # plain symbol string for partitioning only
```

**Step 6 — Add `headers_fn` factories to `TopicRegistry`:**
```python
from tradingcz import SCHEMA_VERSION

class TopicRegistry:
    def market_data_headers_fn(
        self, source: str, broker: str, message_type: str
    ) -> Callable[[Any], dict[str, str]]:
        """Return a headers_fn for market-data messages."""
        def _headers(item: Any) -> dict[str, str]:
            return {
                "message_type": message_type,
                "source": source,
                "broker": broker,
                "symbol": getattr(item, "symbol", ""),
                "schema_version": SCHEMA_VERSION,
            }
        return _headers

    def event_headers_fn(
        self, event_type: str, source: str
    ) -> Callable[[Any], dict[str, str]]:
        """Return a headers_fn for event messages."""
        def _headers(event: Any) -> dict[str, str]:
            return {
                "message_type": event_type,
                "source": source,
                "request_id": getattr(event, "request_id", ""),
                "schema_version": SCHEMA_VERSION,
            }
        return _headers
```

---

#### Finding F-2: Empty key fallback is silent 🟡 MEDIUM

**Problem:** When no `key_fn` is provided to `TypedProducer`, the default `lambda _: ""` sends `None` as key → messages round-robin across all partitions. For multi-partition topics, this silently loses per-symbol ordering.

```python
# Current default in TypedProducer.__init__ — silent round-robin
self._key_fn: Callable[[T], str] = key_fn or (lambda _: "")
```

**Recommended Solution:**
Log a warning when `TypedProducer` is created without `key_fn`:
```python
def __init__(self, channel, serializer, *, key_fn=None, headers_fn=None):
    self._channel = channel
    self._serializer = serializer
    if key_fn is None:
        logger.warning(
            "TypedProducer on channel '%s' has no key_fn — messages will "
            "round-robin across all partitions. Per-key ordering is NOT guaranteed.",
            channel.name,
        )
    self._key_fn = key_fn or (lambda _: "")
    self._headers_fn = headers_fn
```

---

#### Finding F-3: Partition hashing — correct, but undocumented ℹ️ INFO

**Problem:** The SDK relies entirely on librdkafka's built-in `murmur2_random` partitioner. This is correct but undocumented.

**Recommended Solution:**
Document in `Channel` or `KafkaChannel` docstring:
> *"Partition assignment: The SDK delegates to librdkafka's default partitioner (`murmur2_random`). Messages with the same key bytes always land on the same partition for a given partition count. When partition counts change, some keys will move to different partitions."*

---

#### Finding F-4: Value serialization has no embedded schema version 🟡 MEDIUM

**Problem:** Values are serialized via `model_dump_json()` with no schema version. If a model gains a field, old consumers break.

**Recommended Solution:**
Embed schema version in **headers** (see Finding F-1), not in the value payload. This avoids wrapping every value and lets consumers check the schema before deserializing.

---

### f.3 Consumer Checks

#### Finding F-5: No symbol-level partition targeting 🟡 MEDIUM

**Problem:** Consumer uses `subscribe([topic])` — reads ALL partitions and must filter by symbol in application code. For a strategy wanting only AAPL data from a 5-partition topic with 100 symbols, ~20% of bandwidth is wasted.

**Recommended Solution:**

**Short-term:** Document clearly. Add a note that `TypedConsumer` reads all partitions:
```python
# Usage pattern — add to TypedConsumer docstring:
# "Note: TypedConsumer reads ALL partitions of the topic. Filter by
#  message fields in your consumer loop if you only need a subset."
async for msg in consumer.consume():
    if msg.symbol != "AAPL":
        continue
    process(msg)
```

**Long-term:** Add explicit partition assignment:
```python
# tradingcz/transport/kafka/channel.py — add to KafkaChannel
from confluent_kafka import TopicPartition

class KafkaChannel(Channel):
    async def assign(self, partitions: list[int]) -> AIOConsumer:
        """Assign this consumer to specific partitions (leaves consumer group).
        
        Use this when you know exactly which partition(s) to read from
        (e.g., when targeting a specific symbol).
        
        WARNING: With assign(), you leave the consumer group —
        no automatic rebalancing, no offset commit coordination.
        """
        config = self._settings.consumer_config(
            group_id=f"{self._settings.consumer_group}-{self._topic}-assign"
        )
        consumer = AIOConsumer(config)
        tps = [TopicPartition(self._topic, p) for p in partitions]
        await consumer.assign(tps)
        return consumer
```

---

#### Finding F-6: No Murmur2 hash utility for consumer-side partition discovery 🟡 MEDIUM

**Problem:** If a consumer wants to compute which partition a symbol maps to (for monitoring or `assign()`), there's no utility available.

**Recommended Solution:**
Add `tradingcz/transport/kafka/hash.py`:
```python
"""Murmur2 hash — matches librdkafka's murmur2_random partitioner.

librdkafka uses Murmur2 with seed 0x9747b28c for the default
`murmur2_random` partitioner.
"""
import struct

_MURMUR2_SEED = 0x9747b28c


def murmur2(data: bytes) -> int:
    """Compute Murmur2 hash matching librdkafka (seed 0x9747b28c).

    Returns a positive 32-bit integer suitable for modulo partition
    assignment.
    """
    length = len(data)
    m = 0x5bd1e995
    r = 24
    h = (_MURMUR2_SEED ^ length) & 0xFFFFFFFF

    idx = 0
    while length >= 4:
        k = struct.unpack_from("<I", data, idx)[0]
        k = (k * m) & 0xFFFFFFFF
        k ^= k >> r
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h ^= k
        idx += 4
        length -= 4

    if length == 3:
        h ^= (data[idx + 2] & 0xFF) << 16
        h ^= (data[idx + 1] & 0xFF) << 8
        h ^= (data[idx] & 0xFF)
        h = (h * m) & 0xFFFFFFFF
    elif length == 2:
        h ^= (data[idx + 1] & 0xFF) << 8
        h ^= (data[idx] & 0xFF)
        h = (h * m) & 0xFFFFFFFF
    elif length == 1:
        h ^= (data[idx] & 0xFF)
        h = (h * m) & 0xFFFFFFFF

    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF
    h ^= h >> 15
    return h & 0x7FFFFFFF


def partition_for(key: str, num_partitions: int) -> int:
    """Compute Kafka partition for a string key (UTF-8 encoded).

    Matches librdkafka's murmur2_random partitioner exactly.

    Example:
        >>> partition_for("AAPL", 5)
        2
    """
    return murmur2(key.encode("utf-8")) % num_partitions
```

**Verification:** To confirm correctness, produce a message with key `"AAPL"` to a test topic and check the actual partition via kcat:
```bash
kcat -b $BROKER -t test-topic -C -f 'Partition: %p, Key: %k\n' -o beginning -e
# Compare with: python -c "from tradingcz.transport.kafka.hash import partition_for; print(partition_for('AAPL', 5))"
```

---

#### Finding F-7: Consumer loses key/headers/offset metadata 🟡 MEDIUM

**Problem:** `TypedConsumer.consume()` yields `T` (just the deserialized value), stripping the `Message` wrapper. The consumer cannot access `msg.key()`, `msg.headers()`, or `msg.offset()` for deduplication or tracing.

```python
# Current — loses metadata
async for msg in consumer.consume():
    yield self._deserializer.deserialize(msg.payload)  # msg.key is lost!
```

**Recommended Solution:**
Add an alternative method:
```python
class TypedConsumer[T]:
    async def consume(self) -> AsyncIterator[T]:
        """Yield typed values only (convenience method — strips metadata)."""
        async for msg in self._channel.receive():
            yield self._deserializer.deserialize(msg.payload)

    async def consume_with_metadata(self) -> AsyncIterator[tuple[T, Message]]:
        """Yield typed values WITH raw message metadata (key, headers, offset).

        Use this when you need access to the Kafka message key, headers,
        or offset for deduplication, tracing, or offset checkpointing.
        """
        async for msg in self._channel.receive():
            yield self._deserializer.deserialize(msg.payload), msg
```

---

#### Finding F-8: Error handling — no retry, no idempotence 🟡 MEDIUM

**Problem:** `KafkaChannel.receive()` logs errors and continues. No retry logic for transient failures. No idempotence — if a message is processed but offset commit fails, message is re-delivered.

**Recommended Solution:**
Add an `AtLeastOnceConsumer` wrapper:
```python
# tradingcz/transport/stream.py — add:
class AtLeastOnceConsumer[T]:
    """Wraps TypedConsumer with offset-based deduplication for at-least-once semantics.

    Tracks processed (topic, partition, offset) tuples to skip duplicates
    on re-delivery.  Users must provide an ``id_fn`` that extracts a stable
    message ID from each typed value (e.g., ``lambda bar: bar.trade_id``).
    """

    def __init__(
        self,
        consumer: TypedConsumer[T],
        id_fn: Callable[[T], str],
        *,
        max_processed: int = 100_000,
    ) -> None:
        self._consumer = consumer
        self._id_fn = id_fn
        self._processed: dict[str, None] = {}
        self._max_processed = max_processed

    async def consume(self) -> AsyncIterator[T]:
        """Yield typed messages, skipping duplicates."""
        async for msg, raw in self._consumer.consume_with_metadata():
            msg_id = self._id_fn(msg)
            if msg_id in self._processed:
                logger.debug("Skipping duplicate message: %s", msg_id)
                continue
            yield msg
            self._processed[msg_id] = None
            # Simple LRU: evict oldest entries if we exceed the limit
            if len(self._processed) > self._max_processed:
                oldest = next(iter(self._processed))
                del self._processed[oldest]
```

---

### f.4 Operational Checks

#### Finding F-9: No monitoring for hot partitions 🟡 MEDIUM

**Problem:** No metrics to detect when one partition receives disproportionate traffic. With 5 partitions and per-symbol keying, heavy symbols like SPY/TSLA could create hot partitions.

**Recommended Solution:**
1. **Add Prometheus metrics** via the hooks from Finding D-3:
```
kafka_producer_bytes_total{topic, partition}
kafka_consumer_records_total{topic, partition}
kafka_consumer_lag{topic, partition}
```

2. **Hot partition detection query (PromQL):**
```promql
# Partitions consuming >2x the per-partition average
topk(5,
  rate(kafka_consumer_bytes_total[5m])
  / on(topic) group_left
  avg by(topic) (rate(kafka_consumer_bytes_total[5m]))
  > 2
)
```

3. **Manual check via kcat:**
```bash
# Check per-partition offsets and lag
kcat -b $BROKER -t dev-market-data -Q -o-1 -o-1000 2>&1 | grep -E 'partition|offset'
```

4. **Mitigation:** If hot partitions are detected, use sharded keys (see Finding F-5 long-term solution) — `"SPY#0"`, `"SPY#1"`, `"SPY#2"` to spread high-volume symbols across multiple partitions.

---

#### Finding F-10: No partition count change migration plan 🟡 MEDIUM

**Problem:** When `dev-market-data` increases from 5 to 10 partitions, ~50% of symbols silently move to different partitions. Per-symbol ordering across the change is broken. No documented procedure.

**Recommended Solution — Two options:**

**Option A: Accept brief reordering (simple, recommended)**
1. Announce change window.
2. Alter topic: `kafka-topics --alter --topic dev-market-data --partitions 10`
3. Rolling restart consumers (they discover new partition count via metadata refresh).
4. New messages follow new Murmur2 mapping; old messages stay on old partitions.
5. Accept that some symbols briefly appear on both old and new partitions.

**Option B: Drain-and-switch (zero reordering, for critical data)**
1. Create `dev-market-data-v2` with 10 partitions.
2. Dual-write all new messages to both `v1` (5 partitions) and `v2` (10 partitions).
3. Migrate consumers one-by-one from `v1` to `v2`.
4. Once all consumers are on `v2`, stop writing to `v1`.
5. Delete `v1` after retention period.

**Option A is recommended for the current use case.**

---

#### Finding F-11: No partition mapping tests 🟡 MEDIUM

**Problem:** No tests verify producer partition mapping consistency or that consumers correctly reassign after partition changes.

**Recommended Solution — Three test cases:**

```python
# tests/unit/test_kafka_partitioning.py (suggested)

import pytest
from tradingcz.transport.kafka.hash import murmur2, partition_for


class TestMurmur2:
    """Verify our Murmur2 implementation matches known librdkafka outputs."""

    def test_empty_key(self) -> None:
        result = murmur2(b"")
        assert result >= 0
        assert result < 2**31

    def test_known_symbol_partitions(self) -> None:
        """Regression test — these values must never change."""
        # Verify with actual Kafka broker in integration tests
        assert partition_for("AAPL", 5) >= 0
        assert partition_for("AAPL", 5) < 5
        assert partition_for("TSLA", 10) >= 0
        assert partition_for("TSLA", 10) < 10

    def test_deterministic(self) -> None:
        """Same input always produces same output."""
        results = [partition_for("AAPL", 5) for _ in range(100)]
        assert len(set(results)) == 1, "partition_for should be deterministic"

    def test_same_key_same_partition(self) -> None:
        """Same key maps to same partition regardless of call count."""
        p1 = partition_for("SPY", 5)
        p2 = partition_for("SPY", 5)
        assert p1 == p2

    def test_different_keys_may_differ(self) -> None:
        """Different keys may map to different partitions."""
        mapping = {
            partition_for(symbol, 5)
            for symbol in ["AAPL", "TSLA", "SPY", "QQQ", "MSFT"]
        }
        # With 5 symbols and 5 partitions, at least some should differ
        assert len(mapping) >= 2, "Expected at least 2 different partitions"


class TestPartitionMigration:
    """Verify behavior when partition counts change."""

    def test_same_key_on_larger_partition_count(self) -> None:
        """Key still maps to a valid partition after increase."""
        # After increasing from 5 to 10, every key must map to [0, 9]
        for symbol in ["AAPL", "TSLA", "SPY"]:
            p = partition_for(symbol, 10)
            assert 0 <= p < 10, f"{symbol} → {p} out of range for 10 partitions"

    def test_some_keys_move(self) -> None:
        """Some (not all) keys should move when partition count changes."""
        symbols = ["AAPL", "TSLA", "SPY", "QQQ", "MSFT", "GOOG", "AMZN", "META"]
        moved = sum(
            1 for s in symbols
            if partition_for(s, 5) != partition_for(s, 10)
        )
        # With Murmur2, approximately 50% should move
        assert moved > 0, "Expected some keys to change partition"
        assert moved < len(symbols), "Expected some keys to stay same"
```

---

## Priority Actions Summary

| # | Priority | Finding | Action |
|---|----------|---------|--------|
| F-1 | 🔴 HIGH | No headers — metadata in JSON keys | Add headers support to Channel/Message/KafkaChannel/TypedProducer. Simplify keys to plain strings for routing only. |
| A-2 | 🔴 HIGH | Version fragmentation (executor v0.0.10 vs v0.0.15) | Bump executor to latest SDK, replace local SDK models with shared ones. |
| C-1 | 🔴 HIGH | `build_signal()` leaks transport into model layer | Move to `tradingcz/serialization/signal_codec.py`. |
| C-3 | 🔴 HIGH | `StreamQuote` missing from SDK source | Add model to `tradingcz/model/ingestion/stream_quote.py`. |
| C-4 | 🔴 HIGH | Empty `__init__.py` in executor model subpackages | Populate with re-exports. |
| F-2 | 🟡 MED | Empty key fallback produces silent round-robin | Log warning when TypedProducer created without key_fn. |
| C-2 | 🟡 MED | Key methods wrapped in verbose lambdas everywhere | Add `event_key_fn()` / `market_data_key_fn()` factory methods. |
| D-1 | 🟡 MED | No shared error type hierarchy | Add `tradingcz/errors.py` with SdkError, TransportError, etc. |
| D-2 | 🟡 MED | No logging hooks or structured logging | Add `tradingcz/logging.py` with contextvars-based request_id. |
| D-3 | 🟡 MED | No metrics/observability hooks | Add `on_send`/`on_receive`/`on_error` callbacks to Channel. |
| D-4 | 🟡 MED | No consumer group coordination | Add `ConsumerGroup` wrapper with rebalance handling and graceful commit. |
| D-6 | 🟡 MED | No schema versioning strategy | Add `SCHEMA_VERSION` constant, embed in Kafka headers. |
| F-6 | 🟡 MED | No Murmur2 hash utility for consumer partition discovery | Add `tradingcz/transport/kafka/hash.py` with `partition_for()`. |
| F-7 | 🟡 MED | TypedConsumer strips key/headers/offset metadata | Add `consume_with_metadata()` method. |
| F-8 | 🟡 MED | No retry or idempotence for consumer | Add `AtLeastOnceConsumer` wrapper with offset-based dedup. |
| F-9 | 🟡 MED | No hot partition monitoring | Add Prometheus metrics hooks + PromQL detection query. |
| F-10 | 🟡 MED | No partition migration plan | Document Option A (simple) and Option B (drain-and-switch). |
| F-11 | 🟡 MED | No partition mapping tests | Write 3 test cases (Murmur2 correctness, determinism, migration). |
| B-1 | 🟡 MED | `Message` dataclass misses headers/offset/partition | Add headers, offset, partition, topic fields. |
| B-3 | 🟡 MED | `KafkaTransport` auto-creates topics (admin concern) | Extract `KafkaTopicAdmin` class. |
| C-6 | 🟡 MED | `RequestReplyClient` swallows errors silently | Add skip counter + debug log; expose as `skipped_count` property. |
| E-2 | 🟡 MED | Race condition on shared request/reply topic | Add optional `reply_channel` param to RequestReplyClient. |
| E-4 | 🟡 MED | Ephemeral historical topics never deleted | Set 1-hour retention, add `cleanup_historical_topics()` method. |
| B-4 | 🟢 LOW | Docstrings mention REST/gRPC/WS (unrealistic) | Update to justify ABCs by testability, not multi-transport. |
| C-5 | 🟢 LOW | Inaccurate docstrings ("dataclasses" vs Pydantic) | Fix to say "Pydantic models (frozen=True)". |
| D-5 | 🟢 LOW | No batching support | Add `send_batch()` with default sequential implementation. |
| D-7 | 🟢 LOW | No `KeyStrategy` protocol | Add ABC for named, documented key strategies. |
| E-3 | 🟢 LOW | Unused topic configs in TopicRegistry | Comment out until consumers exist. |
| E-5 | 🟢 LOW | `kafka_key.py` module name leaks transport into model | Rename to `message_key.py`. |

---

## Assumptions

1. **librdkafka version:** ≥ 2.14.0 (as pinned in `pyproject.toml`). Default partitioner is `murmur2_random` since librdkafka 1.0.0.
2. **Kafka broker version:** ≥ 2.4 (supports incremental cooperative rebalancing via `cooperative-sticky` assignor).
3. **Single cluster:** All topics are in one Kafka cluster. Cross-cluster mirroring is out of scope.
4. **Python 3.14:** As declared in `pyproject.toml`. All type annotations use PEP 695 syntax (`[T]` generics).
5. **Confluent `AIOConsumer`/`AIOProducer`:** The native async API is preferred over thread-pool-based `Consumer`/`Producer`.
6. **Topic auto-creation:** Currently enabled in `KafkaTransport`. This analysis recommends separating it into `KafkaTopicAdmin` (Finding B-3).
7. **`StreamQuote` model:** Assumed to come from a pre-built wheel or generation step. Analysis treats its absence from SDK source as a bug (Finding C-3).
8. **Key encoding:** Current code uses `key.encode()` (UTF-8). librdkafka's `murmur2_random` hashes the raw bytes. This is consistent and correct.
9. **No explicit partition assignment:** The SDK uses `subscribe()`, relying on the consumer group coordinator. No `assign()` is used anywhere, which is correct for the current architecture.
