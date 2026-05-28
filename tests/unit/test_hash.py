"""Unit tests for tradingcz.transport.hash (Murmur2, partition_for)."""

from tradingcz.transport.hash import murmur2, partition_for


class TestMurmur2:
    """Tests for Murmur2 hash matching librdkafka."""

    def test_empty_bytes(self) -> None:
        h = murmur2(b"")
        assert h >= 0
        assert h <= 0x7FFFFFFF

    def test_non_empty(self) -> None:
        h = murmur2(b"test")
        assert h >= 0
        assert isinstance(h, int)

    def test_deterministic(self) -> None:
        a = murmur2(b"AAPL")
        b = murmur2(b"AAPL")
        assert a == b

    def test_different_inputs_different_hash(self) -> None:
        """Different inputs SHOULD produce different hashes (high probability)."""
        a = murmur2(b"AAPL")
        b = murmur2(b"TSLA")
        # These could theoretically collide, but extremely unlikely
        # with quality hash function on 2 distinct inputs.
        assert a != b

    def test_result_is_positive_31bit(self) -> None:
        for s in [b"", b"A", b"AAPL", b"very long symbol name here"]:
            h = murmur2(s)
            assert 0 <= h <= 0x7FFFFFFF, f"hash({s!r}) = {h} out of range"


class TestPartitionFor:
    """Tests for partition_for (Kafka partition assignment)."""

    def test_partition_in_range(self) -> None:
        for key in ["AAPL", "TSLA", "SPY", "MSFT", "GOOGL"]:
            p = partition_for(key, 5)
            assert 0 <= p < 5, f"partition_for({key}, 5) = {p} out of range"

    def test_single_partition(self) -> None:
        for key in ["AAPL", "TSLA", ""]:
            assert partition_for(key, 1) == 0

    def test_deterministic(self) -> None:
        a = partition_for("AAPL", 10)
        b = partition_for("AAPL", 10)
        assert a == b

    def test_different_partitions_for_different_keys(self) -> None:
        """With 100 partitions, different keys should map to different partitions
        with very high probability (collision chance ~1%)."""
        p1 = partition_for("AAPL", 100)
        p2 = partition_for("MSFT", 100)
        # Could collide but extremely unlikely
        assert p1 != p2

    def test_same_key_different_partitions_count(self) -> None:
        p3 = partition_for("AAPL", 3)
        p5 = partition_for("AAPL", 5)
        # Same hash, different modulo — different partition
        assert p3 != p5
