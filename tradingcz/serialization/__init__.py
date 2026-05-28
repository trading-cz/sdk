"""Serialization layer — pluggable codecs for typed message data.

Layer 1 of the transport stack: converts between typed domain models
and raw bytes.  JSON is the default; future codecs (Avro, Protobuf)
implement the same ``Codec[T]`` interface.
"""

from tradingcz.serialization.json_codec import JsonCodec
from tradingcz.serialization.protocol import Codec, Deserializer, Serializer

__all__ = [
    "Codec",
    "Deserializer",
    "JsonCodec",
    "Serializer",
]
