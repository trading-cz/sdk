"""KafkaMessage — honest wrapper around a Kafka message.

Carries Kafka-specific fields (offset, partition, topic) without pretending
to be transport-agnostic.  Used by KafkaChannel.receive().
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class KafkaMessage:
    """A message received from a Kafka topic.

    All fields reflect what Kafka actually provides — no abstraction.
    """

    payload: bytes
    """Raw message value (JSON bytes in our system)."""

    key: str = ""
    """Message key (plain string, decoded from UTF-8 bytes)."""

    headers: dict[str, str] = field(default_factory=dict)
    """Message headers (key → value, both decoded as UTF-8 strings)."""

    offset: int = -1
    """Kafka offset of this message (-1 if unknown)."""

    partition: int = -1
    """Kafka partition this message was read from (-1 if unknown)."""

    topic: str = ""
    """Kafka topic name."""


__all__ = ["KafkaMessage"]
