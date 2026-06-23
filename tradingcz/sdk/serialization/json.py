"""JSON serializer / deserializer for Pydantic models."""

from typing import cast

from pydantic import BaseModel, ValidationError

from tradingcz.sdk.exceptions import SerializationError
from tradingcz.sdk.serialization.protocol import Deserializer, Serializer


class JsonSerializer[T: BaseModel](Serializer[T]):
    def serialize(self, value: T) -> bytes:
        """Serialize *value* to UTF-8 JSON bytes, omitting null fields."""
        return cast(str, value.model_dump_json(exclude_none=True)).encode()


class JsonDeserializer(Deserializer):
    def deserialize[T: BaseModel](self, payload: bytes, *, model_type: type[T]) -> T:
        """Deserialize UTF-8 JSON bytes into an instance of *model_type*."""
        try:
            return cast(T, model_type.model_validate_json(payload))
        except ValidationError as exc:
            raise SerializationError(f"Failed to deserialize {model_type.__name__}: {exc}") from exc


__all__ = ["JsonDeserializer", "JsonSerializer"]
