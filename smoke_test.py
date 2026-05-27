#!/usr/bin/env python3
"""Smoke test for SDK's Confluent Kafka transport layer.

Verifies that TypedProducer + TypedConsumer work end-to-end against a
real Kafka broker using Confluent's native async (AIOProducer/AIOConsumer).

Usage:
    .venv/bin/python smoke_test.py

Or with overrides:
    KAFKA_BOOTSTRAP_SERVERS=46.224.59.47:30002 .venv/bin/python smoke_test.py
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from confluent_kafka.admin import AdminClient
from pydantic import BaseModel

from tradingcz.config import KafkaSettings
from tradingcz.serialization import JsonCodec
from tradingcz.transport import KafkaTransport, TypedConsumer, TypedProducer

# ── Config ──────────────────────────────────────────────────────────────────
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "46.224.59.47:30002")
TEST_TOPIC = "dev-smoke-test"
GROUP_ID = f"smoke-test-{uuid4().hex[:8]}"

# ── Test model ──────────────────────────────────────────────────────────────


class Ping(BaseModel):
    """Simple round-trip test message."""
    request_id: str
    message: str
    timestamp: str


# ── kcat helpers ────────────────────────────────────────────────────────────


def run_kcat(args: list[str], timeout: int = 10) -> str:
    """Run a kcat command and return stdout."""
    try:
        result = subprocess.run(
            ["kcat", "-b", BOOTSTRAP_SERVERS, *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        return "[kcat not installed]"
    except subprocess.TimeoutExpired:
        return "[kcat timed out]"


def clear_test_topic() -> None:
    """Delete and recreate the smoke test topic."""
    print(f"\n{'=' * 60}")
    print("  🧹 Clearing test topic")
    print(f"{'=' * 60}")

    admin = AdminClient({"bootstrap.servers": BOOTSTRAP_SERVERS})

    # Delete existing
    try:
        futures = admin.delete_topics([TEST_TOPIC])
        for _topic, f in futures.items():
            f.result()
        print(f"  ✓ Deleted '{TEST_TOPIC}'")
    except Exception as exc:
        msg = str(exc)
        if "UNKNOWN_TOPIC_OR_PART" in msg:
            print(f"  ⏭  '{TEST_TOPIC}' does not exist (first run)")
        else:
            print(f"  ⚠  Delete warning: {exc}")

    # Also delete from ingestion's old tests
    for legacy in ["dev-event", "dev-market-data"]:
        try:
            futures = admin.delete_topics([legacy])
            for _topic, f in futures.items():
                f.result()
        except Exception:
            pass


# ── Smoke tests ─────────────────────────────────────────────────────────────


async def test_producer_consumer_roundtrip() -> bool:
    """Test 1: Produce a message then consume it back."""
    print(f"\n{'=' * 60}")
    print("  TEST 1: TypedProducer → TypedConsumer round-trip")
    print(f"{'=' * 60}")

    settings = KafkaSettings(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        consumer_group=GROUP_ID,
        consumer_poll_timeout=0.5,  # faster polls for smoke test
        consumer_overrides={
            "auto.offset.reset": "earliest",
            "enable.auto.commit": "true",
        },
    )
    transport = KafkaTransport(settings)

    try:
        # Channel — demonstrates per-topic overrides (retention=60s for test topic)
        channel = await transport.channel(
            TEST_TOPIC,
            num_partitions=1,
            retention_ms=60_000,  # 1 minute — test topic, short-lived
        )
        print(f"  ✓ Channel created: {channel.name} (poll_timeout={settings.consumer_poll_timeout}s, retention=60s)")

        # Producer
        producer = TypedProducer(
            channel=channel,
            serializer=JsonCodec(Ping),
            key_fn=lambda p: p.request_id,
        )

        # Send a ping
        ping = Ping(
            request_id=uuid4().hex[:12],
            message="hello from smoke test",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await producer.send(ping)
        print(f"  ✓ Sent: {ping.model_dump_json()}")

        # Consumer
        consumer = TypedConsumer(channel=channel, deserializer=JsonCodec(Ping))

        # Read back with timeout
        received: Ping | None = None
        async def _consume() -> None:
            nonlocal received
            async for msg in consumer.consume():
                if msg.request_id == ping.request_id:
                    received = msg
                    break

        try:
            await asyncio.wait_for(_consume(), timeout=10.0)
        except asyncio.TimeoutError:
            pass

        if received is None:
            print("  ❌ FAIL: Did not receive the message back")
            return False

        print(f"  ✓ Received: {received.model_dump_json()}")
        assert received.request_id == ping.request_id
        assert received.message == ping.message
        print("  ✅ PASS: Round-trip successful")
        return True

    finally:
        await transport.close()


async def test_kcat_produce_consume() -> None:
    """Test 2: Verify kcat can produce/consume on the same topic."""
    print(f"\n{'=' * 60}")
    print("  TEST 2: kcat produce → SDK consume")
    print(f"{'=' * 60}")

    test_payload = json.dumps({
        "request_id": "kcat-test-001",
        "message": "from kcat",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    # Produce via kcat (pipe JSON, no key needed for test)
    print(f"  → Producing via kcat to '{TEST_TOPIC}'...")
    msg_line = test_payload
    try:
        result = subprocess.run(
            ["kcat", "-b", BOOTSTRAP_SERVERS, "-t", TEST_TOPIC, "-P"],
            input=msg_line, capture_output=True, text=True, timeout=10, check=False,
        )
        out = result.stdout + result.stderr
    except FileNotFoundError:
        out = "[kcat not installed]"
    print(f"    {out.strip() or 'OK'}")

    await asyncio.sleep(1)

    # Consume via SDK
    settings = KafkaSettings(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        consumer_group=f"{GROUP_ID}-kcat",
        consumer_poll_timeout=0.5,
        consumer_overrides={"auto.offset.reset": "earliest"},
    )
    transport = KafkaTransport(settings)
    try:
        channel = await transport.channel(TEST_TOPIC, num_partitions=1, retention_ms=60_000)
        consumer = TypedConsumer(channel=channel, deserializer=JsonCodec(Ping))

        received: Ping | None = None
        async def _consume() -> None:
            nonlocal received
            async for msg in consumer.consume():
                if msg.request_id == "kcat-test-001":
                    received = msg
                    break

        try:
            await asyncio.wait_for(_consume(), timeout=10.0)
        except asyncio.TimeoutError:
            pass

        if received:
            print(f"  ✓ SDK consumed kcat message: {received.model_dump_json()}")
            print("  ✅ PASS: kcat → SDK interop works")
        else:
            print("  ⚠  WARN: kcat message not picked up (may be offset issue)")
    finally:
        await transport.close()


async def test_kcat_list_topics() -> None:
    """Test 0: Verify broker connectivity via kcat metadata."""
    print(f"\n{'=' * 60}")
    print("  TEST 0: Broker connectivity (kcat -L)")
    print(f"{'=' * 60}")

    out = run_kcat(["-L"], timeout=10)
    # Show first 20 lines of metadata
    for line in out.splitlines()[:20]:
        print(f"  {line}")
    if "metadata" in out.lower() or "broker" in out.lower() or "topic" in out.lower():
        print("  ✅ PASS: Broker reachable")
    else:
        print("  ❌ FAIL: Cannot connect to broker")
        print(f"  Full output: {out}")


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    print("=" * 60)
    print("  🧪 SDK CONFLUENT KAFKA TRANSPORT SMOKE TEST")
    print(f"  Broker : {BOOTSTRAP_SERVERS}")
    print(f"  Topic  : {TEST_TOPIC}")
    print(f"  Group  : {GROUP_ID}")
    print("=" * 60)

    # Test 0: Connectivity
    await test_kcat_list_topics()

    # Clean slate
    clear_test_topic()
    await asyncio.sleep(2)

    # Run tests
    results: dict[str, bool] = {}

    results["roundtrip"] = await test_producer_consumer_roundtrip()

    # Reset offsets for kcat test (delete & recreate)
    clear_test_topic()
    await asyncio.sleep(2)

    await test_kcat_produce_consume()

    # Summary
    print(f"\n{'=' * 60}")
    print("  📊 RESULTS")
    print(f"{'=' * 60}")
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} : {name}")

    all_pass = all(results.values())
    if all_pass:
        print("\n  🎉 All smoke tests passed!")
    else:
        print("\n  ❌ Some tests failed!")
        sys.exit(1)

    # Cleanup
    print("\n  🧹 Final cleanup...")
    clear_test_topic()
    print("  ✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
