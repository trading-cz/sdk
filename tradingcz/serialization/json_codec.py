"""JSON codec — serialize/deserialize any Pydantic model via JSON.

Usage::

    from tradingcz.serialization import JsonCodec
    from tradingcz.model.ingestion import Bar

    codec = JsonCodec(Bar)
    payload = codec.serialize(bar)          # bytes
    bar2 = codec.deserialize(payload)       # Bar
"""

from pydantic import BaseModel

from tradingcz.serialization.protocol import Codec


class JsonCodec[T: BaseModel](Codec[T]):
    """JSON codec backed by Pydantic ``model_dump_json`` / ``model_validate_json``.

    Type parameter ``T`` must be a Pydantic ``BaseModel`` subclass.
    """

    def __init__(self, model_type: type[T]) -> None:
        self._model = model_type

    def serialize(self, value: T) -> bytes:
        """Serialize *value* to UTF-8 JSON bytes."""
        return value.model_dump_json().encode()

    def deserialize(self, payload: bytes) -> T:
        """Deserialize UTF-8 JSON bytes into a model instance."""
        return self._model.model_validate_json(payload)

    def content_type(self) -> str:
        return "application/json"
