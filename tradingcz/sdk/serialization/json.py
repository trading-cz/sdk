"""JSON serializer / deserializer for Pydantic models.

Usage::

    from tradingcz.sdk.serialization import JsonDeserializer, JsonSerializer
    from tradingcz.sdk.models.market import Bar

    # Serialize-only (polymorphic, any Pydantic model):
    serializer = JsonSerializer()
    payload = serializer.serialize(bar)              # bytes

    # Deserialize-only (pass target type at call time):
    deserializer = JsonDeserializer()
    bar2 = deserializer.deserialize(payload, model_type=Bar)
"""

from pydantic import BaseModel, ValidationError

from tradingcz.sdk.exceptions import SerializationError
from tradingcz.sdk.serialization.protocol import Deserializer, Serializer


class JsonSerializer[T: BaseModel](Serializer[T]):
    """Serialize-only JSON serializer — no model type required.

    Use this with :class:`TypedProducer` when the channel carries
    heterogeneous model types (e.g. ``Trade | Bar | Quote``).
    Serialization is polymorphic via Pydantic's ``model_dump_json``.
    """

    def serialize(self, value: T) -> bytes:
        """Serialize *value* to UTF-8 JSON bytes, omitting null fields."""
        return value.model_dump_json(exclude_none=True).encode()  # type: ignore[no-any-return]


class JsonDeserializer(Deserializer):
    """Type-agnostic JSON deserializer — pass target model at call time.

    Create once, reuse for any Pydantic model::

        deserializer = JsonDeserializer()
        bar = deserializer.deserialize(payload, model_type=Bar)
        trade = deserializer.deserialize(payload, model_type=Trade)
    """

    def deserialize[T: BaseModel](self, payload: bytes, *, model_type: type[T]) -> T:
        """Deserialize UTF-8 JSON bytes into an instance of *model_type*.

        Raises:
            SerializationError: If payload is not valid JSON or doesn't match the model.
        """
        try:
            return model_type.model_validate_json(payload)  # type: ignore[no-any-return]
        except ValidationError as exc:
            raise SerializationError(f"Failed to deserialize {model_type.__name__}: {exc}") from exc


__all__ = ["JsonDeserializer", "JsonSerializer"]
