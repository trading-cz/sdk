# SDK Active TODO — PR #49 (feature/market-data-add-latest-bar-trades)

## Issue 1 (Pre-existing): Circular Import — `registry.py` ↔ event models

### The import chain that deadlocks

```
registry.py  ──imports──▶  models/__init__.py  ──imports──▶  models/events/__init__.py
    ▲                                                                      │
    │                                                                      ▼
    └──── imports register_event ────  data_request_event.py  ◀────────────┘
```

**Step by step** — when **any** code imports from `registry.py` first:

| Step | Module | Action |
|------|--------|--------|
| 1 | `registry.py` | Begins init. Line 18: `from models.enums.event import EventType` |
| 2 | `models/__init__.py` | Python must init the `models` package first |
| 3 | `models/events/__init__.py` | Package init triggers `from models.events import ...` |
| 4 | `data_request_event.py` | Line 29: `from tradingcz.sdk.registry import register_event` |
| 5 | 💥 | `registry` is **still being initialized** (step 1 hasn't finished) → `ImportError` |

### Which event models trigger it

All 5 event models import `register_event` from `registry`:

```
models/events/data_request_event.py      → from tradingcz.sdk.registry import register_event
models/events/service_request_event.py   → from tradingcz.sdk.registry import register_event
models/events/trading_signal_event.py    → from tradingcz.sdk.registry import register_event
models/events/lifecycle_event.py         → from tradingcz.sdk.registry import register_event
models/events/execution_request_event.py → from tradingcz.sdk.registry import register_event
```

### Root cause

`registry.py` imports `EventType` + `MarketDataType` at module level:

```python
# registry.py (line 18)
from tradingcz.sdk.models.enums.event import EventType, MarketDataType
```

But every use of those symbols is in a **type annotation**, and `registry.py` already has `from __future__ import annotations` (line 11), which means **all annotations are strings at runtime**. The import is unnecessary at runtime.

### Why it went unnoticed

This only triggers when `registry.py` is imported **before** `models`. Many import paths happen to hit `models` first (e.g., via `messaging/__init__.py` → `fire_and_forget.py` → `EventRegistry`), but the `test_event_router.py` test hits `messaging.router` → `messaging/__init__.py` → `fire_and_forget.py` → `registry.py` **first**, exposing the circularity.

### Recommended fix

Remove the runtime import; use `TYPE_CHECKING`:

**Before** (`registry.py`, lines 16-18):
```python
from tradingcz.sdk.exceptions import RegistryError
from tradingcz.sdk.lang.model_registry import ModelRegistry
from tradingcz.sdk.models.enums.event import EventType, MarketDataType
```

**After**:
```python
from __future__ import annotations  # already present at line 11

from typing import TYPE_CHECKING

from tradingcz.sdk.exceptions import RegistryError
from tradingcz.sdk.lang.model_registry import ModelRegistry

if TYPE_CHECKING:
    from tradingcz.sdk.models.enums.event import EventType, MarketDataType
```

That's it — one line changed. `from __future__ import annotations` already makes all `EventType` / `MarketDataType` annotations strings at runtime, so no other code changes needed. The decorators `register_event(event_type: EventType)` and `register_market_data(data_type: MarketDataType)` never use `EventType`/`MarketDataType` as runtime values — they just pass them through to `EventRegistry.register()` / `MarketDataRegistry.register()`.

---

## Issue 2: `_DataTransport` bypasses L2 (raw `TransportConsumer` + manual deserialize)

### Architecture rule being violated

From `.github/skills/architecture-advisor/SKILL.md`:

> **Known Violations**
> `_request_historical` (~line 243): Uses raw `TransportConsumer` + `model_validate_json()` instead of `TypedConsumer`
> **Fix**: Use `TypedConsumer` for deserialization, keep dedup/filtering in application code

> **Common Pitfall #5**: Using `TransportConsumer` directly in application code: Always go through `TypedConsumer` for typed access.

### Layer model

```
L1: TransportConsumer     — raw bytes, Kafka protocol       ← _DataTransport uses THIS directly
L2: TypedConsumer         — Pydantic deserialization        ← _DataTransport should use THIS
L3: EventRouter/...       — messaging patterns, routing
```

`_DataTransport` is application code (above L2). It's doing L2's job manually.

### What's wrong — `request_historical()` (lines 134-157)

```python
# _transport.py — current code (VIOLATION)
consumer = TransportConsumer(resp.data_topic, self._settings, f"data-{uuid.uuid4().hex[:8]}")
try:
    async for msg in consumer:                          # L1: raw bytes
        if msg.headers.get(Header.EVENT_ID) != correlation_id:
            continue                                     # L3: correlation filtering
        seq = msg.headers.get(Header.SEQUENCE, "")
        if seq and self._dedup.is_duplicate(...):
            continue                                     # L3: dedup
        try:
            item = model_type.model_validate_json(msg.payload)  # ← L2: manual deserialize!
        except Exception:
            logger.debug("Skipping unparseable %s", ...)
            continue
        results.setdefault(item.symbol, []).append(item)
```

Three layers mixed in one loop: L1 (raw consume) + L2 (manual `model_validate_json`) + L3 (correlation filter, dedup).

### What's wrong — `stream()` (lines 198-217)

Same pattern:
```python
# _transport.py — current code (VIOLATION)
consumer = TransportConsumer(resp.data_topic, self._settings, f"stream-{uuid.uuid4().hex[:8]}")

async def _consume() -> AsyncIterator[T]:
    try:
        async for msg in consumer:                    # L1
            seq = msg.headers.get(Header.SEQUENCE, "")
            if seq and self._dedup.is_duplicate(...):
                continue                               # L3
            try:
                parsed = model_type.model_validate_json(msg.payload)  # ← L2: manual!
            except Exception:
                continue
            yield parsed
```

### Recommended fix

Use `TypedConsumer` (L2) for deserialization. Application code keeps only its own concerns (correlation filter, dedup, symbol grouping).

**After — `request_historical()`**:
```python
from tradingcz.sdk.registry import EventRegistry
from tradingcz.sdk.typed.typed_consumer import TypedConsumer

# Build types dict for TypedConsumer (L2 handles deserialization)
event_type = str(EventRegistry.event_type_for(model_type))
data_types: dict[str, type[BaseModel]] = {event_type: model_type}

consumer = TypedConsumer(
    resp.data_topic,
    self._settings,
    data_types,
    group_suffix=f"data-{uuid.uuid4().hex[:8]}",
    auto_commit=False,
)
try:
    async for _event_type, model, msg in consumer:   # L2: already deserialized!
        if model is None:
            continue                                   # unknown type (won't happen here)
        if msg.headers.get(Header.EVENT_ID) != correlation_id:
            continue                                   # L3: correlation filter
        seq = msg.headers.get(Header.SEQUENCE, "")
        if seq and self._dedup.is_duplicate(
            msg.headers.get(Header.SOURCE, msg.headers.get(Header.SOURCE_APP, "")),
            seq,
        ):
            continue                                   # L3: dedup
        results.setdefault(model.symbol, []).append(model)
        count += 1
        if expected and count >= expected:
            break
finally:
    await consumer.close()  # TypedConsumer.close() is needed (or context manager)
```

**After — `stream()`**:
```python
event_type = str(EventRegistry.event_type_for(model_type))
data_types: dict[str, type[BaseModel]] = {event_type: model_type}

consumer = TypedConsumer(
    resp.data_topic,
    self._settings,
    data_types,
    group_suffix=f"stream-{uuid.uuid4().hex[:8]}",
    auto_commit=False,
)

async def _consume() -> AsyncIterator[T]:
    try:
        async for _event_type, model, msg in consumer:  # L2: deserialized
            if model is None:
                continue
            seq = msg.headers.get(Header.SEQUENCE, "")
            if seq and self._dedup.is_duplicate(
                msg.headers.get(Header.SOURCE, msg.headers.get(Header.SOURCE_APP, "")),
                seq,
            ):
                continue                                 # L3: dedup
            yield model                                  # type: ignore[return-value]
    finally:
        await consumer.close()
```

### What changes

| Before | After |
|--------|-------|
| `TransportConsumer(...)` | `TypedConsumer(..., types={str(event_type): model_type})` |
| `async for msg in consumer:` (raw) | `async for _event_type, model, msg in consumer:` (typed) |
| `model_type.model_validate_json(msg.payload)` | Gone — `model` is already a Pydantic instance |
| `try/except Exception` for parse errors | Gone — L2 handles parse errors silently (yields `None` or raises `SdkError` → `on_error`) |
| Correlation filter, dedup | Stay — these are L3 concerns, correctly in application code |

Note: `TypedConsumer` may need a `.close()` method. If it doesn't have one yet, you'd need to add it (delegates to `TransportConsumer.close()`).
