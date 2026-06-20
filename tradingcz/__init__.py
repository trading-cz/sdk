"""Top-level ``tradingcz`` namespace.

Each sub-package lives in its own distribution (namespace package):

    tradingcz.sdk       — SDK library (shared models, transport, framework)
    tradingcz.ingestion — Market data ingestion service
    tradingcz.strategy  — Trading strategies
    tradingcz.executor  — Order execution engine
    tradingcz.risk      — Risk management

Public SDK API (``tradingcz.sdk``):
    - tradingcz.sdk.transport       — TransportProducer, TransportConsumer, KafkaSettings, KafkaTopicAdmin
    - tradingcz.sdk.typed           — TypedProducer, TypedConsumer
    - tradingcz.sdk.messaging       — EventRouter, FireAndForget, RequestReply, ReplayConsumer
    - tradingcz.sdk.health          — HealthMonitor, HealthPublisher
    - tradingcz.sdk.serialization   — Serializer, Deserializer, JsonSerializer, JsonDeserializer
    - tradingcz.sdk.models.market   — Bar, Quote, Trade, etc.
    - tradingcz.sdk.models.events   — TradingSignal, DataRequest, etc.
    - tradingcz.sdk.indicators      — ATR, SMA, etc.
    - tradingcz.sdk.service_app     — ServiceApp (application facade)
"""

from pathlib import Path
from pkgutil import extend_path

# Schema version — embedded in every Kafka message header for compatibility checks.
SCHEMA_VERSION = "1.0"

# Allow `tradingcz.*` portions from multiple distributions.
__path__ = extend_path(__path__, __name__)

_generated_tradingcz = Path(__file__).resolve().parents[1] / "generated" / "tradingcz"
if _generated_tradingcz.is_dir():
    __path__.append(str(_generated_tradingcz))
