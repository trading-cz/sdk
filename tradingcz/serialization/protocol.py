"""Serialization protocol — abstract codec interfaces.

All codecs are generic in the type they encode/decode.
Layer 1 of the transport stack — sits above ``Channel`` (bytes)
and below ``TypedProducer`` / ``TypedConsumer`` (typed models).
"""

from abc import ABC, abstractmethod


class Serializer[T](ABC):
    """Serialize typed values to raw bytes."""

    @abstractmethod
    def serialize(self, value: T) -> bytes:
        """Convert *value* to bytes."""

    @abstractmethod
    def content_type(self) -> str:
        """MIME type of the serialized form (e.g. ``"application/json"``)."""

    def serialize_batch(self, values: list[T]) -> list[bytes]:
        """Serialize a batch of values.

        Default implementation calls ``serialize()`` for each value.
        Override for more efficient bulk serialization.
        """
        return [self.serialize(v) for v in values]


class Deserializer[T](ABC):
    """Deserialize raw bytes to typed values."""

    @abstractmethod
    def deserialize(self, payload: bytes) -> T:
        """Parse *payload* into a typed value."""


class Codec[T](Serializer[T], Deserializer[T], ABC):
    """Combined serializer + deserializer for a given type ``T``."""
