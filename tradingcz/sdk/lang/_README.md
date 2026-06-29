# lang — Language-Level Utilities

Pure Python utilities — no Kafka, no I/O. Used across all layers.

## Components

| Class/Function | Role |
| ---------------- | ------ |
| `Lazy[T]` | Descriptor — init value on first access (used by `KafkaTransport._producer`) |
| `FactoryRegistry[K, V]` | Decorator-based IoC registry — key → (class, factory) |
| `ModelRegistry[K]` | Decorator-based type registry — bidirectional key ↔ Pydantic model |
| `Retry` | Async retry wrapper — call any operation with retries |
| `setup_shutdown_handlers` | Register SIGTERM/SIGINT → set `asyncio.Event` |

---

## Lazy — lazy-initialized descriptor

```python
from tradingcz.sdk.lang import Lazy

class ExpensiveClient:
    _connection = Lazy(lambda self: connect_to_db(self._db_url))

    def __init__(self, db_url: str):
        self._db_url = db_url

    def query(self, sql: str):
        conn = self._connection  # connect_to_db() called on FIRST access only
        return conn.execute(sql)
```text

---

## FactoryRegistry — key → (class, factory)

```python
from tradingcz.sdk.lang import FactoryRegistry

adapters = FactoryRegistry[str, type]()

@adapters.register("alpaca")
class AlpacaAdapter:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

@adapters.register("ibkr", factory=lambda cls, **kw: cls(**kw, gateway="ib-gw"))
class IBKRAdapter:
    def __init__(self, api_key: str, gateway: str) -> None:
        ...

# Lookup:
cls, factory = adapters.get("alpaca")
instance = factory(cls=cls, api_key="pk_live_...")

cls, factory = adapters.get("ibkr")
instance = factory(cls=cls, api_key="...")  # gateway="ib-gw" baked in
```text

> For **bidirectional key ↔ model** mapping (used by TypedConsumer, EventRouter
> for Kafka header dispatch), see `ModelRegistry` below.

---

## ModelRegistry — bidirectional key ↔ Pydantic model

`ModelRegistry[K]` is a **class-level** bidirectional registry.  Unlike
`FactoryRegistry[K, V]` (instance-based, stores factories), `ModelRegistry`
stores bare model classes and supports reverse lookup.

```python
from tradingcz.sdk.lang.model_registry import ModelRegistry

# Create a concrete registry:
class EventRegistry(ModelRegistry[EventType]):
    """EventType ↔ Pydantic model."""

class MarketDataRegistry(ModelRegistry[MarketDataType]):
    """MarketDataType ↔ Pydantic model."""
```

**Register models via decorator:**

```python
@EventRegistry.register(EventType.BAR)
class Bar(BaseModel):
    symbol: str
    ...

# Or use the convenience decorators from sdk.registry:
from tradingcz.sdk.registry import register_event, register_market_data

@register_event(EventType.BAR)
@register_market_data(MarketDataType.BARS)
class Bar(BaseModel): ...
```

**Lookup:**

```python
EventRegistry.model_for(EventType.BAR)       # → Bar
EventRegistry.key_for(Bar)                   # → EventType.BAR (or None)
EventRegistry.event_type_for(Bar)            # → EventType.BAR (raises if missing)
MarketDataRegistry.data_type_for(Bar)        # → MarketDataType.BARS (or None)
```

**Key differences from `FactoryRegistry[K, V]`:**

| | `FactoryRegistry[K, V]` | `ModelRegistry[K]` |
|---|---|---|
| Storage | Instance-based | Class-level (static) |
| Value | `(class, factory)` tuple | Bare model class |
| Lookup | One-way: `get(key)` | Bidirectional: `model_for(key)` + `key_for(model)` |
| Purpose | Runtime IoC construction | Wire-protocol deserialization |
| Subclassing | Not needed (instantiate directly) | Required (concrete key type) |

---

## Retry — async operation with retries

```python
from tradingcz.sdk.lang import Retry

retry = Retry(max_retries=5, delay=2.0)

# Retry any async callable on Exception:
result = await retry.call(lambda: app.stock.bars(["AAPL"], days=30))
# → 6 attempts total (1 initial + 5 retries), 2s between retries

print(retry.attempts)  # number of retries actually used
```text

> `CancelledError` and `KeyboardInterrupt` propagate immediately — never retried.

---

## setup_shutdown_handlers — graceful shutdown

```python
import asyncio
from tradingcz.sdk.lang import setup_shutdown_handlers

async def main():
    shutdown = asyncio.Event()
    setup_shutdown_handlers(shutdown)

    # ... start services ...

    await shutdown.wait()  # blocks until SIGTERM or SIGINT
    # ... graceful cleanup ...
```text
