"""Murmur2 hash — matches librdkafka's murmur2_random partitioner.

librdkafka uses Murmur2 with seed 0x9747b28c for the default
``murmur2_random`` partitioner.  This module provides a pure-Python
implementation for consumer-side partition discovery.

Usage::

    from tradingcz.sdk.core.transport.hash_utils import partition_for

    p = partition_for("AAPL", 5)  # → which partition AAPL maps to
"""

# TODO: smazat?

import struct

_MURMUR2_SEED = 0x9747B28C


def murmur2(data: bytes) -> int:
    """Compute Murmur2 hash matching librdkafka (seed 0x9747b28c).

    Args:
        data: Raw bytes to hash (typically a UTF-8 encoded key string).

    Returns:
        A positive 32-bit integer suitable for modulo partition assignment.
    """
    length = len(data)
    m = 0x5BD1E995
    r = 24
    h = (_MURMUR2_SEED ^ length) & 0xFFFFFFFF

    idx = 0
    while length >= 4:
        k = struct.unpack_from("<I", data, idx)[0]
        k = (k * m) & 0xFFFFFFFF
        k ^= k >> r
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h ^= k
        idx += 4
        length -= 4

    if length == 3:
        h ^= (data[idx + 2] & 0xFF) << 16
        h ^= (data[idx + 1] & 0xFF) << 8
        h ^= data[idx] & 0xFF
        h = (h * m) & 0xFFFFFFFF
    elif length == 2:
        h ^= (data[idx + 1] & 0xFF) << 8
        h ^= data[idx] & 0xFF
        h = (h * m) & 0xFFFFFFFF
    elif length == 1:
        h ^= data[idx] & 0xFF
        h = (h * m) & 0xFFFFFFFF

    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF
    h ^= h >> 15
    return h & 0x7FFFFFFF


def partition_for(key: str, num_partitions: int) -> int:
    """Compute the Kafka partition for a given string key.

    Matches librdkafka's ``murmur2_random`` partitioner exactly:
    the key is UTF-8 encoded, hashed with Murmur2, then taken modulo
    the partition count.

    Args:
        key: The message key (plain string, e.g. ``"AAPL"``).
        num_partitions: Total partition count for the topic.

    Returns:
        Zero-based partition index in ``[0, num_partitions)``.

    Example:
        >>> partition_for("AAPL", 5)
        2
    """
    return murmur2(key.encode("utf-8")) % num_partitions


__all__ = ["murmur2", "partition_for"]
