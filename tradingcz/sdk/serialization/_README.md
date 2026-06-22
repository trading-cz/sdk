# serialization — Layer 2: Typed Serialization

Bridge between raw bytes (Layer 1) and typed Pydantic models. Used by `TypedProducer` / `TypedConsumer` in the messaging layer.

## Architecture position

```text
┌─────────────────────────────────────────┐
│  EventRouter / RequestReply / F&F       │  ← Layer 3: Messaging
├─────────────────────────────────────────┤
│  TypedProducer / TypedConsumer / Parser │  ← Layer 2: Typed wrappers
├─────────────────────────────────────────┤
│  THIS PACKAGE                           │  ← Serialize/deserialize
├─────────────────────────────────────────┤
│  KafkaChannel                           │  ← Layer 1: Raw bytes
└─────────────────────────────────────────┘
```

## Components

| Class | Role |
| ------- | ------ |
| `Serializer[T]` | Abstract: typed value → bytes |
| `Deserializer[T]` | Abstract: bytes → typed value |
| `Codec[T]` | Combined Serializer + Deserializer |
| `JsonSerializer[T]` | Serialize any Pydantic model to JSON (polymorphic) |
| `JsonCodec[T]` | Round-trip JSON codec for a specific Pydantic model |

## JsonCodec — round-trip for a known model type

```python
from tradingcz.sdk.serialization import JsonCodec
from tradingcz.sdk.models.market import Bar

codec = JsonCodec(Bar)

bar = Bar(symbol="AAPL", timestamp=..., open=150.0, ...)

# Serialize
payload: bytes = codec.serialize(bar)
# → b'{"symbol":"AAPL","open":150.0,...}'

# Deserialize
bar2: Bar = codec.deserialize(payload)
assert bar2.symbol == "AAPL"
```

## JsonSerializer — serialize any model (polymorphic)

Use when a channel carries heterogeneous types (e.g. `Trade | Bar | Quote`):

```python
from tradingcz.sdk.serialization import JsonSerializer
from tradingcz.sdk.models.market import Bar, Trade

serializer = JsonSerializer()

bar_bytes = serializer.serialize(Bar(...))
trade_bytes = serializer.serialize(Trade(...))
# Both produce valid JSON bytes — no type check at serialize time
```text

## Custom codec (example)

```python
from tradingcz.sdk.serialization import Serializer, Deserializer

class AvroSerializer[T](Serializer[T]):
    def serialize(self, value: T) -> bytes:
        ...  # Avro encoding

    def content_type(self) -> str:
        return "application/avro"

class AvroDeserializer[T](Deserializer[T]):
    def deserialize(self, payload: bytes) -> T:
        ...  # Avro decoding
```
