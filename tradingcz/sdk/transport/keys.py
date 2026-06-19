"""Kafka message keys — typed value object for message routing."""

from __future__ import annotations

import typing

from pydantic import BaseModel, ConfigDict


class KafkaKey(BaseModel):
    """Typed Kafka message key — thin value object.

    Converts to/from wire format (``str``) at the Layer 1/2 boundary.
    No factory methods — callers construct keys directly.
    """

    model_config = ConfigDict(frozen=True)
    value: str

    def to_kafka(self) -> str:
        """Convert to Kafka wire format (plain string)."""
        return self.value

    @classmethod
    def from_kafka(cls, key: str) -> typing.Self:
        """Construct from Kafka wire format (plain string)."""
        return cls(value=key)


__all__ = ["KafkaKey"]
