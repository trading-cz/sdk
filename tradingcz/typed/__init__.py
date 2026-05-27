"""Typed stream layer — generic producer and consumer over typed models.

Layer 2 of the transport stack: wraps a ``Channel`` with a ``Codec[T]``
to provide type-safe send/consume operations.

Services compose these from SDK building blocks::

    from tradingcz.typed import TypedProducer, TypedConsumer
    from tradingcz.serialization import JsonCodec
    from tradingcz.transport import KafkaTransport
"""

from tradingcz.typed.stream import TypedConsumer, TypedProducer

__all__ = [
    "TypedConsumer",
    "TypedProducer",
]
