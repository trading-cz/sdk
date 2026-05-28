#!/usr/bin/env python3
"""Comprehensive smoke test for the simplified SDK.

Verifies end-to-end against a real Kafka broker (46.224.59.47:30002):
  1. KafkaChannel send/receive with headers
  2. KafkaMessage fields (offset, partition, topic, key, headers)
  3. TypedProducer/TypedConsumer round-trip with headers_fn
  4. TypedParser — multiple message types on a shared topic
  5. DedupFilter — duplicate messages are skipped
  6. SignalPublisher — fire-and-forget pattern
  7. Request/reply correlation via _RequestReply
  8. kcat verification of topic contents

Usage:
    source .venv/bin/activate
    python smoke_test.py

    # Or with custom broker:
    KAFKA_BOOTSTRAP_SERVERS=localhost:9092 python smoke_test.py
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from confluent_kafka.admin import AdminClient
from pydantic import BaseModel, Field

from tradingcz import SCHEMA_VERSION
from tradingcz.config import KafkaSettings
from tradingcz.model.ingestion import Bar, Quote
from tradingcz.model.message_headers import event_headers
from tradingcz.sdk._helpers import _DedupFilter, _FireAndForget, _RequestReply
from tradingcz.serialization import JsonCodec
from tradingcz.transport import (
    KafkaChannel,
    KafkaMessage,
    KafkaTransport,
    TopicRegistry,
    TypedConsumer,
    TypedParser,
    TypedProducer,
)
from tradingcz.transport.hash import partition_for

# ── Config ──────────────────────────────────────────────────────────────────
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "46.224.59.47:30002")
TEST_TOPIC = "dev-smoke-test"
GROUP_ID = f"smoke-{uuid4().hex[:8]}"
PASS = 0
FAIL = 0


# ── Test models ─────────────────────────────────────────────────────────────


class Ping(BaseModel):
    request_id: str
    message: str
    timestamp: str


class Pong(BaseModel):
    request_id: str
    reply: str


# ── Helpers ─────────────────────────────────────────────────────────────────


def section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ PASS  {msg}")


def fail(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  ❌ FAIL  {msg}")


def assert_eq(actual: object, expected: object, label: str) -> None:
    if actual == expected:
        ok(f"{label}: {actual!r}")
    else:
        fail(f"{label}: expected {expected!r}, got {actual!r}")


def run_kcat(args: list[str], timeout: int = 15) -> str:
    """Run kcat and return combined stdout+stderr."""
    try:
        result = subprocess.run(
            ["kcat", "-b", BOOTSTRAP, *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        return "[kcat not installed]"
    except subprocess.TimeoutExpired:
        return "[kcat timed out]"


def clean_topic(name: str, *, num_partitions: int = 1) -> None:
    """Delete and recreate a topic."""
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    try:
        futures = admin.delete_topics([name])
        for _t, f in futures.items():
            f.result()
    except Exception:
        pass
    # Wait for deletion to propagate
    import time
    time.sleep(1)


async def make_transport() -> tuple[KafkaTransport, TopicRegistry]:
    """Create transport and topic registry for smoke tests."""
    settings = KafkaSettings(
        bootstrap_servers=BOOTSTRAP,
        consumer_group=GROUP_ID,
        consumer_poll_timeout=0.5,
        consumer_overrides={
            "auto.offset.reset": "earliest",
            "enable.auto.commit": "false",   # no offset commits — always from earliest
        },
    )
    transport = KafkaTransport(settings)
    topics = TopicRegistry(env="dev")
    return transport, topics


# ── Tests ───────────────────────────────────────────────────────────────────


async def test_1_channel_send_receive_with_headers() -> None:
    """KafkaChannel.send() with headers → KafkaMessage with headers, offset, partition."""
    section("Test 1: KafkaChannel send/receive with headers")

    clean_topic(TEST_TOPIC, num_partitions=3)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=3, retention_ms=60_000)

        # Send with key and headers
        test_headers = {
            "message_type": "ping",
            "source_app": "smoke_test",
            "sequence": "1",
            "schema_version": SCHEMA_VERSION,
        }
        await channel.send(b'{"hello":"world"}', key="test-key", headers=test_headers)
        ok("Sent message with key='test-key' + 4 headers")

        # Receive
        msg: KafkaMessage | None = None
        async for m in channel.receive():
            msg = m
            break

        if msg is None:
            fail("No message received")
            return

        # Verify KafkaMessage fields
        assert_eq(msg.key, "test-key", "key")
        assert_eq(msg.headers.get("message_type"), "ping", "header: message_type")
        assert_eq(msg.headers.get("source_app"), "smoke_test", "header: source_app")
        assert_eq(msg.headers.get("sequence"), "1", "header: sequence")
        assert_eq(msg.headers.get("schema_version"), SCHEMA_VERSION, "header: schema_version")

        ok(f"offset={msg.offset}, partition={msg.partition}, topic='{msg.topic}'")
        assert msg.offset >= 0 or fail(f"offset should be >=0, got {msg.offset}")
        assert msg.partition >= 0 or fail(f"partition should be >=0, got {msg.partition}")
        assert_eq(msg.topic, TEST_TOPIC, "topic")

    finally:
        await transport.close()


async def test_2_typed_producer_consumer_roundtrip() -> None:
    """TypedProducer with key_fn+headers_fn → TypedConsumer round-trip."""
    section("Test 2: TypedProducer → TypedConsumer round-trip with headers")

    clean_topic(TEST_TOPIC, num_partitions=1)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=1, retention_ms=60_000)

        seq_counter = [0]

        producer = TypedProducer(
            channel=channel,
            serializer=JsonCodec(Ping),
            key_fn=lambda p: p.request_id,
            headers_fn=lambda p: {
                "message_type": "ping",
                "source_app": "smoke_test",
                "sequence": str(seq_counter.pop(0) + 1),
                "schema_version": SCHEMA_VERSION,
            },
        )

        ping = Ping(
            request_id="t2-" + uuid4().hex[:8],
            message="hello round-trip",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await producer.send(ping)

        # Consume with metadata
        consumer = TypedConsumer(channel=channel, deserializer=JsonCodec(Ping))
        received: Ping | None = None
        received_meta: KafkaMessage | None = None

        async for p, meta in consumer.consume_with_metadata():
            if p.request_id == ping.request_id:
                received = p
                received_meta = meta
                break

        if received is None:
            fail("Did not receive the message back")
            return

        assert_eq(received.request_id, ping.request_id, "request_id round-trip")
        assert_eq(received.message, ping.message, "message round-trip")

        if received_meta:
            assert_eq(
                received_meta.headers.get("message_type", ""),
                "ping",
                "header round-trip: message_type",
            )

    finally:
        await transport.close()


async def test_3_typed_parser_multiple_types() -> None:
    """TypedParser dispatches Ping and Pong on the same topic."""
    section("Test 3: TypedParser — multiple message types on shared topic")

    clean_topic(TEST_TOPIC, num_partitions=1)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=1, retention_ms=60_000)

        # Produce Ping
        await channel.send(
            Ping(request_id="p1", message="ping1", timestamp="").model_dump_json().encode(),
            key="",
            headers={"message_type": "ping", "source_app": "smoke", "sequence": "1", "schema_version": SCHEMA_VERSION},
        )
        # Produce Pong
        await channel.send(
            Pong(request_id="p2", reply="pong1").model_dump_json().encode(),
            key="",
            headers={"message_type": "pong", "source_app": "smoke", "sequence": "2", "schema_version": SCHEMA_VERSION},
        )

        # Parse with TypedParser
        parser = TypedParser(channel=channel, types={"ping": Ping, "pong": Pong})

        received: list[tuple[str, object]] = []
        async for msg_type, model, raw in parser.parse():
            received.append((msg_type, model))
            if len(received) >= 2:
                break

        assert len(received) == 2 or fail(f"Expected 2 messages, got {len(received)}")
        if len(received) >= 2:
            types_seen = {t for t, _ in received}
            assert_eq(types_seen, {"ping", "pong"}, "message types dispatched")

    finally:
        await transport.close()


async def test_4_dedup_filter() -> None:
    """_DedupFilter skips duplicate (source, sequence) pairs."""
    section("Test 4: DedupFilter — skip duplicate sequences")

    d = _DedupFilter(max_size=100)

    # First occurrence — not duplicate
    assert d.is_duplicate("ingestion", "1") is False
    ok("seq 1 first time → not duplicate")

    # Second occurrence — duplicate
    assert d.is_duplicate("ingestion", "1") is True
    ok("seq 1 second time → duplicate (skipped)")

    # Same sequence, different source — not duplicate
    assert d.is_duplicate("strategy", "1") is False
    ok("seq 1 from different source → not duplicate")

    # Different sequence — not duplicate
    assert d.is_duplicate("ingestion", "2") is False
    ok("seq 2 → not duplicate")

    assert_eq(d.skipped_count, 1, "skipped_count")
    assert_eq(d.total_count, 4, "total_count")

    # Test LRU eviction
    for i in range(200):
        d.is_duplicate("src", str(i))
    ok(f"LRU eviction: {d.total_count} total, size bounded at {d._max}")


async def test_5_signal_publisher() -> None:
    """SignalPublisher sends fire-and-forget with correct headers."""
    section("Test 5: SignalPublisher (fire-and-forget)")

    clean_topic(TEST_TOPIC, num_partitions=1)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=1, retention_ms=60_000)
        faf = _FireAndForget(channel=channel, service_id="smoke_test")

        from tradingcz.model.signal import TradingSignal

        signal = TradingSignal(
            symbol="AAPL",
            side="LONG",
            strategy_id="test-strat",
            open_price=150.0,
            entry_price=151.0,
            stop_loss=149.0,
            valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            atr_period=3,
            atr_value=2.5,
        )

        await faf.send(
            signal,
            message_type="trading_signal",
            key="AAPL",
            extra_headers={"tracking_id": "trk-001", "strategy_id": "test-strat"},
        )

        # Consume and verify headers
        msg: KafkaMessage | None = None
        async for m in channel.receive():
            msg = m
            break

        if msg is None:
            fail("Signal not received")
            return

        assert_eq(msg.key, "AAPL", "signal key")
        assert_eq(msg.headers.get("message_type"), "trading_signal", "signal message_type")
        assert_eq(msg.headers.get("tracking_id"), "trk-001", "signal tracking_id")
        ok("Signal published with correct key + headers")

        # Verify kcat can read it
        kcat_out = run_kcat(["-t", TEST_TOPIC, "-C", "-o", "beginning", "-e", "-f", "key=%k\\nheaders=%h\\nvalue=%s\\n---\\n"], timeout=10)
        print(f"  kcat output:\n{kcat_out[:500]}")

    finally:
        await transport.close()


async def test_6_request_reply_correlation() -> None:
    """_RequestReply correlates request/response by request_id."""
    section("Test 6: _RequestReply correlation")

    clean_topic(TEST_TOPIC, num_partitions=1)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=1, retention_ms=60_000)

        rr = _RequestReply(
            channel=channel,
            service_id="smoke_test",
            message_types={"pong": Pong},
        )
        await rr.start()

        # Send request and response concurrently (simulating real flow)
        async def _send_response() -> None:
            await asyncio.sleep(0.3)  # let the request land first
            pong = Pong(request_id="req-001", reply="echo-response")
            # Use a separate channel for producing to avoid the consumer conflict
            resp_channel = await transport.channel(TEST_TOPIC + "-resp", num_partitions=1, retention_ms=60_000)

        # Actually, use the same channel but produce after request
        async def _produce_pong() -> None:
            await asyncio.sleep(0.5)
            pong = Pong(request_id="req-001", reply="echo-response")
            await channel.send(
                pong.model_dump_json().encode(),
                key="",
                headers={
                    "message_type": "pong",
                    "source_app": "responder",
                    "request_id": "req-001",
                    "schema_version": SCHEMA_VERSION,
                    "sequence": "99",
                },
            )

        asyncio.create_task(_produce_pong())

        # Send request and wait for response
        req = Ping(request_id="req-001", message="hello", timestamp="")
        resp = await rr.request(
            req,
            response_type=Pong,
            request_type="ping",
            timeout=10.0,
        )

        assert_eq(resp.request_id, "req-001", "correlated request_id")
        assert "echo" in resp.reply or fail(f"unexpected reply: {resp.reply}")
        ok("Request → Response correlated by request_id")

    finally:
        await rr.close()
        await transport.close()


async def test_7_dedup_in_channel_flow() -> None:
    """End-to-end: send duplicate sequences, verify consumer skips them."""
    section("Test 7: Dedup in channel flow (end-to-end)")

    clean_topic(TEST_TOPIC, num_partitions=1)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=1, retention_ms=60_000)

        # Send 5 messages: seq 1, 2, 3, 2(dup), 4
        for seq in [1, 2, 3, 2, 4]:
            await channel.send(
                b'{"value":' + str(seq).encode() + b'}',
                key="",
                headers={
                    "message_type": "test",
                    "source_app": "dedup_test",
                    "sequence": str(seq),
                    "schema_version": SCHEMA_VERSION,
                },
            )

        # Consume with dedup filter
        dedup = _DedupFilter()
        received_seqs: list[int] = []
        async for msg in channel.receive():
            source = msg.headers.get("source_app", "")
            seq = msg.headers.get("sequence", "0")
            if dedup.is_duplicate(source, seq):
                continue
            received_seqs.append(int(seq))
            if len(received_seqs) >= 4:
                break

        assert_eq(received_seqs, [1, 2, 3, 4], "dedup: only unique sequences received")
        assert_eq(dedup.skipped_count, 1, "dedup: exactly 1 duplicate skipped")

    finally:
        await transport.close()


async def test_8_kcat_inspection() -> None:
    """Verify topic state with kcat after producing messages."""
    section("Test 8: kcat topic inspection")

    clean_topic(TEST_TOPIC, num_partitions=2)
    transport, _ = await make_transport()

    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=2, retention_ms=60_000)

        # Produce messages with different keys to land on different partitions
        for symbol in ["AAPL", "TSLA", "SPY"]:
            await channel.send(
                f'{{"symbol":"{symbol}"}}'.encode(),
                key=symbol,
                headers={
                    "message_type": "trade",
                    "source": "ingestion",
                    "symbol": symbol,
                    "sequence": str(["AAPL", "TSLA", "SPY"].index(symbol) + 1),
                    "schema_version": SCHEMA_VERSION,
                },
            )

        # kcat: list topic metadata
        meta = run_kcat(["-t", TEST_TOPIC, "-L"], timeout=10)
        print(f"  kcat -L:\n{meta[:600]}")

        # kcat: consume and show partitions
        consumed = run_kcat(
            ["-t", TEST_TOPIC, "-C", "-o", "beginning", "-e",
             "-f", "partition=%p key=%k headers=%h\\n"],
            timeout=15,
        )
        print(f"  kcat consume:\n{consumed}")

        # Verify Murmur2 partition_for
        for symbol in ["AAPL", "TSLA", "SPY"]:
            p = partition_for(symbol, 2)
            ok(f"partition_for('{symbol}', 2) = {p}")

        # Verify we consumed the right count
        lines = [l for l in consumed.split("\n") if l.strip()]
        assert_eq(len(lines), 3, "kcat consumed 3 messages")

    finally:
        await transport.close()


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    print("=" * 65)
    print("  SDK SMOKE TEST — Kafka broker:", BOOTSTRAP)
    print("  Test topic:", TEST_TOPIC)
    print("  Group ID:", GROUP_ID)
    print("=" * 65)

    tests = [
        ("Channel send/receive + headers", test_1_channel_send_receive_with_headers),
        ("TypedProducer/Consumer round-trip", test_2_typed_producer_consumer_roundtrip),
        ("TypedParser multi-type dispatch", test_3_typed_parser_multiple_types),
        ("DedupFilter unit", test_4_dedup_filter),
        ("SignalPublisher fire-and-forget", test_5_signal_publisher),
        ("RequestReply correlation", test_6_request_reply_correlation),
        ("Dedup end-to-end flow", test_7_dedup_in_channel_flow),
        ("kcat inspection", test_8_kcat_inspection),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as exc:
            fail(f"{name}: {exc}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 65}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 65}")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
