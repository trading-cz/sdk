"""KafkaMessage — pure-data wrapper around a Kafka message (no commit capability)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KafkaMessage:
    """A message received from a Kafka topic. Pure data — no commit capability.

    Commit is owned by the receiving layer (:class:`ReceiveSession`,
    :class:`TypedConsumer`, :class:`EventRouter`), not by the message.
    """

    payload: bytes
    key: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    offset: int = -1
    partition: int = -1
    topic: str = ""


__all__ = ["KafkaMessage"]
