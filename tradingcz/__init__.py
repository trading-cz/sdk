"""Top-level `tradingcz` namespace for the trading SDK.

Public SDK API (stable):
    - tradingcz.core.transport      — KafkaChannel, KafkaTransport, TypedProducer, TypedConsumer
    - tradingcz.core.serialization  — Serializer, Deserializer, Codec, JsonCodec
    - tradingcz.common              — KafkaSettings, LoggingSettings, ConfigurationError, SdkError, etc.
    - tradingcz.models.market       — Bar, Quote, Trade, etc.
    - tradingcz.models.events       — TradingSignal, etc.
    - tradingcz.indicators          — ATR, SMA, etc.
    - tradingcz.framework           — TradingApp, ServiceApp (business layer)
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
