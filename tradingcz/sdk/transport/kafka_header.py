"""Kafka header field names and typed header builders."""

from __future__ import annotations

import typing
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.models.enums.event import EventType


class Header(StrEnum):
    """Canonical Kafka header field names (StrEnum)."""

    EVENT_TYPE = "event_type"
    SOURCE_APP = "source_app"
    SEQUENCE = "sequence"
    EVENT_ID = "event_id"
    BROKER = "broker"
    SOURCE = "source"


class KafkaHeader(BaseModel):
    """Base class for all Kafka message headers.

    Provides the wire-format contract: typed Pydantic model
    ↔ flat ``dict[str, str]`` suitable for Kafka headers.

    Every Kafka message must carry at least ``event_type`` and
    ``source_app`` so that consumers can route and attribute messages
    without inspecting the payload.
    """

    model_config = ConfigDict(extra="allow")

    event_type: EventType
    source_app: str

    def to_headers(self) -> dict[str, str]:
        """Convert to Kafka wire format (flat dict with string values)."""
        d = self.model_dump(exclude_none=True)
        return {k: str(v) for k, v in d.items()}

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> typing.Self:
        """Construct from Kafka wire-format headers."""
        return cls(**headers)


class EventHeader(KafkaHeader):
    """Headers for event-topic messages — no sequence field."""

    event_id: str


class DataHeader(KafkaHeader):
    """Headers for data-topic messages — includes sequence for dedup."""

    event_id: str = ""
    sequence: int = 0
    broker: str = ""
    source: str = ""
    symbol: str = ""


__all__ = [
    "Header",
    "KafkaHeader",
    "EventHeader",
    "DataHeader",
]
