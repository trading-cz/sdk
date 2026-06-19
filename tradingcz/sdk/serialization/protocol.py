"""Serialization protocol — abstract serializer/deserializer interfaces.

All interfaces are generic in the type they encode/decode.
Layer 1 of the transport stack — sits above ``Channel`` (bytes)
and below ``TypedProducer`` / ``TypedConsumer`` (typed models).
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class Serializer[T](ABC):
    """Serialize typed values to raw bytes."""

    @abstractmethod
    def serialize(self, value: T) -> bytes:
        """Convert *value* to bytes."""


class Deserializer(ABC):
    """Deserialize raw bytes into typed values.

    Unlike :class:`Serializer`, the type is not bound at construction.
    Callers pass the target model type at deserialization time via
    the ``model_type`` keyword argument.
    """

    @abstractmethod
    def deserialize[T: BaseModel](self, payload: bytes, *, model_type: type[T]) -> T:
        """Parse *payload* into an instance of *model_type*."""
