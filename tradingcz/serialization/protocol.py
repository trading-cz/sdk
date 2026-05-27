"""Serialization protocol — abstract codec interfaces.

All codecs are generic in the type they encode/decode.
Layer 1 of the transport stack — sits above ``Channel`` (bytes)
and below ``TypedProducer`` / ``TypedConsumer`` (typed models).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Serializer(ABC, Generic[T]):
    """Serialize typed values to raw bytes."""

    @abstractmethod
    def serialize(self, value: T) -> bytes:
        """Convert *value* to bytes."""

    @abstractmethod
    def content_type(self) -> str:
        """MIME type of the serialized form (e.g. ``"application/json"``)."""


class Deserializer(ABC, Generic[T]):
    """Deserialize raw bytes to typed values."""

    @abstractmethod
    def deserialize(self, payload: bytes) -> T:
        """Parse *payload* into a typed value."""


class Codec(Serializer[T], Deserializer[T], ABC):
    """Combined serializer + deserializer for a given type ``T``."""
