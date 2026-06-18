"""KafkaMessage — honest wrapper around a Kafka message.

Carries Kafka-specific fields (offset, partition, topic) without pretending
to be transport-agnostic.  Used by KafkaChannel.receive().

Messages obtained from :meth:`KafkaChannel.receive` carry an additional
``commit()`` method that commits the message's offset back to Kafka.
Messages constructed manually (e.g. in tests) do not have this capability
and ``commit()`` raises ``RuntimeError``.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KafkaMessage:
    """A message received from a Kafka topic.

    All fields reflect what Kafka actually provides — no abstraction.

    Messages from :meth:`KafkaChannel.receive` carry a private
    ``_commit_fn`` (attached via ``object.__setattr__``) that
    powers the :meth:`commit` method.
    """

    payload: bytes
    key: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    offset: int = -1
    partition: int = -1
    topic: str = ""

    async def commit(self) -> None:
        """Commit this message's offset to Kafka.

        Only available for messages obtained from
        :meth:`KafkaChannel.receive`.  Raises ``RuntimeError``
        when called on a manually-constructed message (e.g. in tests).
        """
        commit_fn: Callable[[], Awaitable[None]] | None = getattr(
            self, "_commit_fn", None
        )
        if commit_fn is None:
            raise RuntimeError(
                "Commit not available: this KafkaMessage was not "
                "received from KafkaChannel.receive()"
            )
        await commit_fn()


__all__ = ["KafkaMessage"]
