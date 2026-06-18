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
    key: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    offset: int = -1
    partition: int = -1
    topic: str = ""


__all__ = ["KafkaMessage"]
