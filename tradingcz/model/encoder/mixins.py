"""Minimal JSON-only serialization helpers for dataclass models."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Self


class ModelSerde:
    """Lightweight base providing only JSON helpers."""

    @classmethod
    def from_json(cls: type[Self], payload: str | bytes) -> Self:
        raw = payload.decode("utf-8") if isinstance(payload, bytes | bytearray) else payload
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self._serialize_value(asdict(self)), ensure_ascii=False)

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list | tuple):
            return [cls._serialize_value(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._serialize_value(val) for key, val in value.items()}
        return value


__all__ = ["ModelSerde"]
