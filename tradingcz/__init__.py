"""Top-level `tradingcz` namespace for the trading SDK.

Public SDK API (stable):
    - tradingcz.transport        — KafkaChannel, KafkaTransport, TypedProducer, TypedConsumer
    - tradingcz.transport.kafka  — KafkaTransport, KafkaChannel, TopicRegistry
    - tradingcz.serialization    — Serializer, Deserializer, Codec, JsonCodec
    - tradingcz.config           — KafkaSettings, LoggingSettings
    - tradingcz.model            — Bar, Quote, Trade, TradingSignal, etc.
    - tradingcz.indicators       — ATR, SMA, etc.
    - tradingcz.sdk              — TradingApp, DataClient, SignalPublisher, etc. (business layer)
    - tradingcz.errors           — SdkError, TransportError, etc.
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
