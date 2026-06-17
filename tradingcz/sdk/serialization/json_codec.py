"""JSON codec — serialize/deserialize any Pydantic model via JSON.

Usage::

    from tradingcz.sdk.serialization import JsonCodec, JsonSerializer
    from tradingcz.sdk.models.market import Bar

    # Round-trip codec (producer + consumer):
    codec = JsonCodec(Bar)
    payload = codec.serialize(bar)          # bytes
    bar2 = codec.deserialize(payload)       # Bar

    # Serialize-only (e.g. TypedProducer with polymorphic market data):
    serializer = JsonSerializer()
    payload = serializer.serialize(bar)     # bytes
"""

from pydantic import BaseModel

from tradingcz.sdk.serialization.protocol import Codec, Serializer


class JsonSerializer[T: BaseModel](Serializer[T]):
    """Serialize-only JSON codec — no model type required.

    Use this with :class:`TypedProducer` when the channel carries
    heterogeneous model types (e.g. ``Trade | Bar | Quote``).
    Serialization is polymorphic via Pydantic's ``model_dump_json``.
    """

    def serialize(self, value: T) -> bytes:
        """Serialize *value* to UTF-8 JSON bytes, omitting null fields."""
        return value.model_dump_json(exclude_none=True).encode()  # type: ignore[no-any-return]

    def content_type(self) -> str:
        """Return the MIME type for this serializer."""
        return "application/json"


class JsonCodec[T: BaseModel](Codec[T]):
    """JSON codec backed by Pydantic ``model_dump_json`` / ``model_validate_json``.

    Type parameter ``T`` must be a Pydantic ``BaseModel`` subclass.
    """

    def __init__(self, model_type: type[T]) -> None:
        self._model = model_type
        self._serializer: JsonSerializer[T] = JsonSerializer()

    def serialize(self, value: T) -> bytes:
        """Serialize *value* to UTF-8 JSON bytes."""
        return self._serializer.serialize(value)

    def deserialize(self, payload: bytes) -> T:
        """Deserialize UTF-8 JSON bytes into a model instance."""
        return self._model.model_validate_json(payload)  # type: ignore[no-any-return]

    def content_type(self) -> str:
        return "application/json"
