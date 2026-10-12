"""Kafka header field names and typed header builders."""

from __future__ import annotations

import typing
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from tradingcz.sdk.models.enums.event import EventType


class Header(StrEnum):
    """Canonical Kafka header field names (StrEnum)."""

    EVENT_TYPE = "event_type"  # Typed message/event name used for dispatch.
    SOURCE_APP = "source_app"  # Application or service that emitted the message.
    SEQUENCE = "sequence"  # Index of a historical record within its request (0..record_count-1).
    EVENT_ID = "event_id"  # Request, response, or data-stream correlation ID.


class KafkaHeader(BaseModel):
    """Base class for all Kafka message headers — typed model ↔ flat dict."""

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
    """Headers for event-topic messages."""

    event_id: str


class DataHeader(KafkaHeader):
    """Headers for data-topic messages."""

    event_id: str = ""  # Correlates the record with its data request/stream.
    sequence: int | None = None  # Historical records only; lets the reader drop duplicates and name gaps.
    symbol: str = ""  # Symbol carried with the data record.


__all__ = [
    "Header",
    "KafkaHeader",
    "EventHeader",
    "DataHeader",
]
