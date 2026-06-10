# SDK Architecture

Expert reference for the `trading-sdk` internals.  If you just want to *use*
the SDK, see the [README](../README.md).

## Module map

```
tradingcz/
├── __init__.py          # Namespace package, SCHEMA_VERSION
├── config.py            # KafkaSettings, LoggingSettings
├── errors.py            # SdkError, TransportError
│
├── sdk/                 ← PUBLIC API — the only layer you import
│   ├── __init__.py      # TradingApp, ServiceApp
│   ├── _app.py          # TradingApp (strategy/consumer role)
│   ├── _service.py      # ServiceApp (base class for ALL services)
│   ├── _health.py       # HealthPublisher (up → heartbeat → down)
│   ├── _helpers.py      # _RequestReply, _FireAndForget (internal patterns)
│   ├── data.py          # DataClient (historical + streaming)
│   ├── signals.py       # SignalPublisher (fire-and-forget)
│   ├── positions.py     # PositionClient (request/reply)
│   ├── balance.py       # BalanceClient (request/reply)
│   └── orders.py        # OrderClient (request/reply)
│
├── transport/           ← Kafka I/O — flat module, no subpackages
│   ├── __init__.py      # KafkaChannel, KafkaTransport, TopicRegistry, etc.
│   ├── channel.py       # KafkaChannel (send/receive), KafkaTransport
│   ├── topics.py        # TopicRegistry, TopicConfig
│   ├── stream.py        # TypedProducer, TypedConsumer, TypedParser
│   ├── request_reply.py # RequestReplyClient[Req, Resp]
│   ├── kafka_message.py # KafkaMessage (offset, partition, headers, payload)
│   ├── hash.py          # Murmur2 partition discovery
│   └── _dedup.py        # DedupFilter (LRU-based deduplication)
│
│
├── model/                ← Domain models — NO vendor dependencies
│   ├── headers.py        Header constants + make_headers() factory
│   ├── events.py         DataRequest, DataReady, DataError
│   ├── signal.py         TradingSignal
│   ├── health.py         ServiceLifecycle
│   ├── enum/             Timeframe, Adjustment, OrderSide, OrderType
│   ├── ingestion/        Bar, Quote, Trade, Snapshot, StreamQuote
│   └── executor/         Order models (market, limit, bracket, OCO, OTO)
│
├── serialization/        ← Codec interfaces + JSON implementation
│   ├── protocol.py       Serializer[T], Deserializer[T], Codec[T] (abstract)
│   └── json_codec.py     JsonCodec[T] (Pydantic → JSON bytes)
│
├── config/               ← Settings (Pydantic, env-first)
│   └── settings.py       KafkaSettings, LoggingSettings
│
└── indicators/
    └── atr.py            calculate_atr (Wilder method)
```

## Entry points

### `TradingApp` — strategy/consumer role

```python
from tradingcz.sdk import TradingApp

async with TradingApp(service_id="my-strategy") as app:
    app.data       # DataClient    — request historical / streaming data
    app.signals    # SignalPublisher — publish trading signals
    app.positions  # PositionClient  — query positions
    app.balance    # BalanceClient   — query account balance
    app.orders     # OrderClient     — query orders
```

All clients are enabled by default.  Disable what you don't need:
```python
app.with_data(False).with_signals(False)
```

### `ServiceApp` — base class for ALL services

```python
from tradingcz.sdk import ServiceApp

async with ServiceApp(service_id="my-service") as svc:
    svc.service_id      # str
    svc.env             # str (dev/prd)
    svc.source_app      # alias for service_id
    svc.transport       # KafkaTransport
    svc.topics          # TopicRegistry
    svc.events_channel  # KafkaChannel (for lifecycle events)
    svc.wait_for_shutdown()  # block until SIGTERM/SIGINT
```

`TradingApp` extends `ServiceApp` — all base properties are available.

## Design principles

1. **Kafka is the permanent transport.**  No abstract `Channel`/`Transport` layer.
   `KafkaChannel` and `KafkaTransport` are the direct concrete API.

2. **Headers are metadata.**  Message type, source app, schema version, sequence
   number — all in Kafka headers.  The payload is pure JSON.

3. **Messages are honest.**  `KafkaMessage` carries `offset`, `partition`, `topic`
   — no pretense of transport agnosticism.

4. **Key routing uses Murmur2.**  `partition_for("AAPL", 5)` produces the same
   partition as librdkafka's default partitioner.

5. **No vendor types in domain models.**  `tradingcz.model` has zero imports
   from Alpaca, IBKR, Polygon, or any broker SDK.

## Request/Reply flow

```
Strategy                    SDK                       Ingestion
   │                         │                           │
   │  data.request_historical(["AAPL"])                  │
   │────────────────────────>│                           │
   │                         │  DataRequest → Kafka      │
   │                         │──────────────────────────>│
   │                         │                           │── fetch from Alpaca
   │                         │  DataReady ← Kafka        │
   │                         │<──────────────────────────│
   │  returns {symbol: [Bar]}│                           │
   │<────────────────────────│                           │
```

Correlation is by `request_id` header — both request and response carry the same
`request_id`.  `_RequestReply` manages pending futures and dispatches responses.

## Fire-and-Forget flow

```
Strategy                    SDK                       Executor
   │                         │                           │
   │  signals.publish(signal, tracking_id="trk-1")      │
   │────────────────────────>│                           │
   │                         │  TradingSignal → Kafka    │
   │                         │──────────────────────────>│── execute order
   │  (returns immediately)  │                           │
```

No response expected.  Headers carry `message_type=trading_signal`,
`source_app=<service_id>`, `tracking_id`, and `sequence`.

## Configuration

All settings via environment variables (Pydantic `BaseSettings` with `env_prefix`):

| Class             | Prefix   | Key vars                                                                          |
|-------------------|----------|-----------------------------------------------------------------------------------|
| `KafkaSettings`   | `KAFKA_` | `BOOTSTRAP_SERVERS`, `CONSUMER_GROUP`, `PRODUCER_OVERRIDES`, `CONSUMER_OVERRIDES` |
| `LoggingSettings` | `LOG_`   | `LEVEL`                                                                           |

librdkafka pass-through: set `KAFKA_PRODUCER_OVERRIDES='{"linger.ms":"50"}'`
to tune any librdkafka parameter without touching code.

## Testing

Use `tests/fake_kafka.py` — an in-memory Kafka transport backed by
[mockafka-py](https://pypi.org/project/mockafka-py/):

```python
from tests.fake_kafka import FakeKafkaTransport
from tradingcz.config.settings import KafkaSettings

settings = KafkaSettings(
    bootstrap_servers="fake:9092",
    consumer_group="test",
)
transport = FakeKafkaTransport(settings)
channel = await transport.channel("test-topic")
await channel.send(b"hello", key="greeting", headers={"type": "test"})

async for msg in channel.receive():
    assert msg.payload == b"hello"
    break
```

No real Kafka broker needed — everything runs in memory.

## Error handling

```python
from tradingcz.errors import SdkError, TransportError

# All SDK errors inherit from SdkError
# TransportError covers Kafka connection/produce/consume failures
```
