# SDK Changes Summary — `feature/json-kafka-keys`

Overview of all changes made to the `tradingcz` SDK on this branch.
Use this when updating SDK client apps (simple-strategy, ingestion, executor, etc.).

**Policy**: Not backward compatible — we are in the development phase.

---

## 1. Transport Package Restructured — `kafka/` Subpackage

**Rationale**: The `transport/` package now has a clean separation:
- **Transport-agnostic** (`transport/*.py`): `protocol.py`, `stream.py`, `request_reply.py`
- **Kafka-specific** (`transport/kafka/`): `channel.py`, `topics.py`

If REST, gRPC, or WebSocket transports are added later, they go into sibling subpackages
(`transport/rest/`, `transport/grpc/`, etc.).

### New package layout
```
tradingcz/transport/
├── __init__.py           # Re-exports all public API
├── protocol.py           # Abstract: Channel, Transport, Message
├── stream.py             # TypedProducer[T], TypedConsumer[T]  (was typed/)
├── request_reply.py      # RequestReplyClient[Req, Resp]
└── kafka/
    ├── __init__.py       # Re-exports KafkaChannel, KafkaTransport, TopicRegistry
    ├── channel.py        # KafkaChannel, KafkaTransport  (was transport/kafka.py)
    └── topics.py         # TopicRegistry, TopicConfig    (was transport/topics.py)
```

### Import changes

```python
# Before
from tradingcz.topics import TopicRegistry                              # old top-level
from tradingcz.transport.topics import TopicRegistry                    # after first move
from tradingcz.typed import TypedProducer, TypedConsumer                # old typed/

# After
from tradingcz.transport.kafka import TopicRegistry                     # Kafka-specific
from tradingcz.transport import TypedProducer, TypedConsumer            # transport-agnostic
```

All symbols are also re-exported from `tradingcz.transport` for convenience:
```python
from tradingcz.transport import (
    KafkaTransport, TopicRegistry,       # from kafka/
    TypedProducer, TypedConsumer,        # from stream.py
    RequestReplyClient,                  # from request_reply.py
    Channel, Transport, Message,         # from protocol.py
)
```

### `tradingcz.typed` package removed
The `typed/` package no longer exists. Use `from tradingcz.transport import TypedProducer, TypedConsumer`.

---

## 2. `control_plane_key()` → `event_key()`

**Rationale**: The topic is called `events` (→ `dev-event`), but the key method was named
`control_plane_key`. Renamed to `event_key` for consistency with topic naming.

### API change

```python
# Before
key = TopicRegistry.control_plane_key("data_request", "smoke_test", request_id)

# After
key = TopicRegistry.event_key("data_request", "smoke_test", request_id)
```

---

## 3. `ControlPlaneKey` → `EventKey`

**Rationale**: Same consistency fix at the model level. The Pydantic model for event-topic
message keys is now `EventKey` instead of `ControlPlaneKey`.

### Import change

```python
# Before
from tradingcz.model.kafka_key import ControlPlaneKey

# After
from tradingcz.model.kafka_key import EventKey
```

Also re-exported from `tradingcz.model`:
```python
from tradingcz.model import EventKey  # was ControlPlaneKey
```

---

## 4. `ServerSettings` Removed (Dead Code)

**Rationale**: Zero usages across all 7 repositories in the workspace. Purely dead weight.

### What was removed
- `class ServerSettings(BaseSettings)` from `tradingcz/config/settings.py`
- Export from `tradingcz/config/__init__.py`

### Migration
No migration needed — nothing used it. If you had `from tradingcz.config import ServerSettings`,
simply delete the import.

---

## 5. `KafkaSettings` — Mandatory Fields & Default Change

### 5a. `bootstrap_servers` and `consumer_group` are now **required** (no defaults)

```python
# Before — silently used localhost / "service" defaults
settings = KafkaSettings()

# After — MUST provide both
settings = KafkaSettings(
    bootstrap_servers="broker1:9092,broker2:9092",
    consumer_group="my-service",
)
```

If omitted, Pydantic raises a `ValidationError` at startup. This prevents
accidental misconfiguration in production.

**Note**: The `ingestion` repo's `KafkaSettings` subclass still provides
`consumer_group = "ingestion"` as a default, so only `bootstrap_servers` is
strictly required there.

### 5b. `auto.offset.reset` default changed: `"latest"` → `"earliest"`

The `consumer_config()` method now defaults to `"earliest"` instead of `"latest"`.
For financial market data, missing messages is worse than processing duplicates.
Override via `KAFKA_CONSUMER_OVERRIDES='{"auto.offset.reset":"latest"}'` if needed.

### 5c. Duplicate `KafkaSettings` class removed

The plain Python `KafkaSettings` class in `tradingcz/transport/kafka.py` was a
full duplicate of the Pydantic one in `tradingcz/config/settings.py`. Removed.
`transport/kafka.py` now imports from `config/settings.py`.

---

## 6. `model/events.py` — NO CHANGE

**Finding rejected**: The `event_type` field (`Literal["data_request"]`, etc.) is a
**Pydantic discriminated union discriminator** — required for deserializing JSON into
the correct model class. The Python class name doesn't exist in the wire format.
This is correct design, not redundancy.

---

## 7. `request_reply.py` — Error Handling Improvements

### 7a. Narrowed exception handling in `_listen()`

```python
# Before — caught all exceptions silently
except Exception:
    continue

# After — distinguishes expected vs unexpected
except (ValueError, TypeError, LookupError):
    # Expected: message on shared topic not meant for us
    continue
except Exception:
    logger.warning("Unexpected error deserializing message on %s", ..., exc_info=True)
    continue
```

### 7b. Listener crash now rejects pending futures

When the background listener crashes, all pending `request()` futures are now
immediately rejected with `RuntimeError("RequestReplyClient listener crashed")`
instead of hanging until timeout. Same for clean cancellation.

---

## 8. `kafka.py` — Simplified `AIOConsumer` Import

```python
# Before — try/except fallback for old confluent-kafka versions
try:
    from confluent_kafka.aio import AIOConsumer
except ImportError:
    from confluent_kafka import AIOConsumer

# After — direct import (project requires confluent-kafka>=2.14.0)
from confluent_kafka.aio import AIOConsumer
```

---

## Migration Checklist for SDK Consumers

- [ ] Update `from tradingcz.topics` → `from tradingcz.transport.kafka`
- [ ] Update `from tradingcz.transport.topics` → `from tradingcz.transport.kafka`
- [ ] Update `from tradingcz.typed` → `from tradingcz.transport` (TypedProducer, TypedConsumer)
- [ ] Rename `TopicRegistry.control_plane_key(...)` → `TopicRegistry.event_key(...)`
- [ ] Rename `ControlPlaneKey` → `EventKey` in imports and type hints
- [ ] Remove any `ServerSettings` imports (dead code)
- [ ] Provide `bootstrap_servers=` and `consumer_group=` when instantiating `KafkaSettings`
- [ ] Verify `auto.offset.reset` behavior: now defaults to `"earliest"`. Override via
  `KAFKA_CONSUMER_OVERRIDES` if `"latest"` is needed for a specific consumer
- [ ] No changes needed for `model/events.py` (finding was invalid)

### Per-repo status

| Repo | Status |
|------|--------|
| sdk (smoke tests) | ✅ Updated |
| simple-strategy | ✅ Updated |
| ingestion | ✅ Updated |
| executor | ⚠️ Needs review (not on this branch) |
| testing | ⚠️ Needs review (not on this branch) |
