"""Unit tests for tradingcz.serialization.JsonCodec."""

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from tradingcz.core.serialization import JsonCodec


class _TestModel(BaseModel):
    name: str
    value: int
    timestamp: datetime


class TestJsonCodec:
    """Tests for JsonCodec round-trip serialization."""

    def test_roundtrip(self) -> None:
        codec = JsonCodec(_TestModel)
        original = _TestModel(
            name="test",
            value=42,
            timestamp=datetime(2026, 5, 28, tzinfo=UTC),
        )
        payload = codec.serialize(original)
        assert isinstance(payload, bytes)
        restored = codec.deserialize(payload)
        assert restored.name == original.name
        assert restored.value == original.value

    def test_content_type(self) -> None:
        codec = JsonCodec(_TestModel)
        assert codec.content_type() == "application/json"

    def test_serialize_returns_bytes(self) -> None:
        codec = JsonCodec(_TestModel)
        original = _TestModel(
            name="test",
            value=1,
            timestamp=datetime(2026, 5, 28, tzinfo=UTC),
        )
        payload = codec.serialize(original)
        assert isinstance(payload, bytes)
        # Should be valid UTF-8 JSON
        payload.decode("utf-8")

    def test_deserialize_invalid_json_raises(self) -> None:
        codec = JsonCodec(_TestModel)
        with pytest.raises((ValueError, Exception)):
            codec.deserialize(b"not json")

    def test_serialize_batch(self) -> None:
        codec = JsonCodec(_TestModel)
        originals = [
            _TestModel(name="a", value=1, timestamp=datetime(2026, 5, 28, tzinfo=UTC)),
            _TestModel(name="b", value=2, timestamp=datetime(2026, 5, 28, tzinfo=UTC)),
        ]
        payloads = codec.serialize_batch(originals)
        assert len(payloads) == 2
        assert all(isinstance(p, bytes) for p in payloads)
        # Deserialize back
        assert codec.deserialize(payloads[0]).name == "a"
        assert codec.deserialize(payloads[1]).name == "b"
