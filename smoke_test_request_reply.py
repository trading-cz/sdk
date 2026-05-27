#!/usr/bin/env python3
"""Smoke test for RequestReplyClient against a real Kafka broker.

Validates:
  1. RequestReplyClient can send a DataRequest and receive a DataReady/DataError.
  2. The client properly correlates responses by request_id.
  3. Timeout handling works.
  4. Multiple concurrent requests don't interfere.

All wiring is inlined — no dependency on simple-strategy helpers.

Usage:
    # Single request (requires ingestion running):
    python smoke_test_request_reply.py

    # With custom broker:
    KAFKA_BOOTSTRAP_SERVERS=46.224.59.47:30002 python smoke_test_request_reply.py

    # Validate with kcat in another terminal:
    kcat -b 46.224.59.47:30002 -t dev-event -C -f 'key=%k\\nvalue=%s\\n---\\n'
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from tradingcz.config import KafkaSettings
from tradingcz.model.events import DataError, DataReady, DataRequest, parse_event
from tradingcz.serialization import JsonCodec
from tradingcz.serialization.protocol import Deserializer
from tradingcz.transport.kafka import TopicRegistry
from tradingcz.transport import KafkaTransport, RequestReplyClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smoke_test")

KAFKA_BOOTSTRAP = "46.224.59.47:30002"
TIMEOUT = 30.0

_Response = DataReady | DataError


# ---------------------------------------------------------------------------
# Inline data response deserializer (same pattern as simple-strategy helper)
# ---------------------------------------------------------------------------


class _DataResponseDeserializer(Deserializer[_Response]):
    """Deserialize only DataReady/DataError, skipping other event types."""

    def deserialize(self, payload: bytes) -> _Response:
        """Parse *payload*; raises ValueError if not a data response."""
        event = parse_event(payload)
        if isinstance(event, (DataReady, DataError)):
            return event
        raise ValueError(f"Not a data response: {type(event).__name__}")

    def content_type(self) -> str:
        """Return the MIME type (JSON)."""
        return "application/json"


def _make_data_client(
    channel: object,
    timeout: float = TIMEOUT,
) -> RequestReplyClient[DataRequest, _Response]:
    """Create a RequestReplyClient configured for DataRequest → DataReady|DataError."""
    # pylint: disable=import-outside-toplevel
    from tradingcz.transport.protocol import Channel  # noqa: F811

    return RequestReplyClient[DataRequest, _Response](
        channel=channel,  # type: ignore[arg-type]
        request_serializer=JsonCodec(DataRequest),
        response_deserializer=_DataResponseDeserializer(),
        request_id_of=lambda r: r.request_id,
        response_id_of=lambda r: r.request_id,
        timeout=timeout,
    )


def print_separator(title: str) -> None:
    """Print a visual separator with a title."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Test 1: Basic request/reply — send a historical DataRequest
# ---------------------------------------------------------------------------


async def test_historical_request() -> bool:
    """Send a historical DataRequest and wait for the response.

    Requires ingestion-historical service to be running.
    """
    print_separator("Test 1: Historical DataRequest → DataReady")

    transport = KafkaTransport(
        KafkaSettings(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            consumer_group="smoke-test-historical",
        )
    )
    topics = TopicRegistry(env="dev")

    events_channel = await transport.channel(topics.events.name)
    logger.info("Connected to events channel: %s", events_channel.name)

    try:
        async with _make_data_client(events_channel) as client:
            end = datetime.now(UTC)
            start = end - timedelta(days=5)

            request = DataRequest(
                type="historic",
                asset="stock",
                broker="alpaca",
                symbols=["SPY"],
                timeframe="1d",
                start_time=start,
                end_time=end,
            )

            logger.info(
                "Sending DataRequest: request_id=%s symbols=%s timeframe=%s",
                request.request_id,
                request.symbols,
                request.timeframe,
            )

            try:
                response = await client.request(request)
            except TimeoutError:
                logger.warning(
                    "Timeout waiting for response (ingestion-historical may not be running). "
                    "Check with: kcat -b %s -t %s -C -o end -f 'key=%%k\\nvalue=%%s\\n---\\n'",
                    KAFKA_BOOTSTRAP,
                    topics.events.name,
                )
                return False

            if isinstance(response, DataError):
                logger.error(" Got DataError: %s", response.error)
                return False

            if isinstance(response, DataReady):
                logger.info(
                    " Got DataReady: topic=%s bar_count=%d",
                    response.data_topic,
                    response.bar_count,
                )

                # Try to consume a few bars to verify the data channel works
                data_channel = await transport.channel(response.data_topic)
                bar_count = 0
                async for msg in data_channel.receive():
                    bar_count += 1
                    if bar_count >= 3 or bar_count >= (response.bar_count or 0):
                        break

                logger.info(" Consumed %d bars from data channel", bar_count)
                return bar_count > 0

            logger.error(" Unexpected response type: %s", type(response).__name__)
            return False

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# Test 2: Concurrent requests
# ---------------------------------------------------------------------------


async def test_concurrent_requests() -> bool:
    """Send two requests concurrently — verify they don't interfere."""
    print_separator("Test 2: Concurrent requests")

    transport = KafkaTransport(
        KafkaSettings(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            consumer_group="smoke-test-concurrent",
        )
    )
    topics = TopicRegistry(env="dev")
    events_channel = await transport.channel(topics.events.name)

    try:
        async with _make_data_client(events_channel) as client:
            end = datetime.now(UTC)
            start = end - timedelta(days=3)

            req1 = DataRequest(
                type="historic",
                asset="stock",
                broker="alpaca",
                symbols=["AAPL"],
                timeframe="1d",
                start_time=start,
                end_time=end,
            )
            req2 = DataRequest(
                type="historic",
                asset="stock",
                broker="alpaca",
                symbols=["MSFT"],
                timeframe="1d",
                start_time=start,
                end_time=end,
            )

            logger.info(
                "Sending 2 concurrent requests: %s, %s",
                req1.request_id[:8],
                req2.request_id[:8],
            )

            results = await asyncio.gather(
                client.request(req1),
                client.request(req2),
                return_exceptions=True,
            )

            ok = True
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(" Request %d failed: %s", i + 1, result)
                    ok = False
                elif isinstance(result, DataError):
                    logger.error(" Request %d: DataError: %s", i + 1, result.error)
                    ok = False
                elif isinstance(result, DataReady):
                    logger.info(
                        " Request %d OK: topic=%s bar_count=%d",
                        i + 1,
                        result.data_topic,
                        result.bar_count,
                    )
                else:
                    logger.error(" Request %d: unexpected type %s", i + 1, type(result).__name__)
                    ok = False

            return ok

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# Test 3: Timeout handling
# ---------------------------------------------------------------------------


async def test_timeout() -> bool:
    """Verify that requests time out when no response arrives.

    Sends a request with an unrecognized type that no handler will
    pick up, so the client should time out.
    """
    print_separator("Test 3: Timeout handling")

    transport = KafkaTransport(
        KafkaSettings(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            consumer_group="smoke-test-timeout",
        )
    )
    topics = TopicRegistry(env="dev")
    events_channel = await transport.channel(topics.events.name)

    try:
        async with _make_data_client(events_channel, timeout=3.0) as client:
            request = DataRequest(
                type="historic",  # type: ignore[arg-type]
                asset="stock",
                broker="alpaca",
                symbols=["NOBODY_HANDLES_THIS"],
                timeframe="1d",
                start_time=datetime.now(UTC) - timedelta(days=1),
                end_time=datetime.now(UTC),
            )

            logger.info("Sending request that nobody will answer (timeout=3s)...")
            try:
                await client.request(request)
                logger.error(" Should have timed out!")
                return False
            except TimeoutError:
                logger.info(" Correctly timed out after 3s")
                return True
            except Exception as exc:
                logger.error(" Unexpected exception: %s", exc)
                return False

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# Test 4: kcat validation helper (informational)
# ---------------------------------------------------------------------------


def show_kcat_info() -> None:
    """Print kcat commands for manual validation."""
    print_separator("Manual validation with kcat")

    topics = TopicRegistry(env="dev")

    print(
        f"""
Run these in another terminal to watch the event flow:

  # Watch all events on the events topic:
  kcat -b {KAFKA_BOOTSTRAP} -t {topics.events.name} -C -o end -f 'key=%k\\nvalue=%s\\n---\\n'

  # Watch market data stream:
  kcat -b {KAFKA_BOOTSTRAP} -t {topics.market_data.name} -C -o end -f 'key=%k\\nvalue=%s\\n---\\n'

  # List all topics:
  kcat -b {KAFKA_BOOTSTRAP} -L
"""
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run all smoke tests."""
    print_separator("RequestReplyClient Smoke Tests")
    print(f"  Broker : {KAFKA_BOOTSTRAP}")
    print(f"  Timeout: {TIMEOUT}s")
    print()

    results: dict[str, bool] = {}

    # Test timeout first (fast, no external dependency beyond Kafka)
    results["timeout"] = await test_timeout()

    # These require ingestion service running
    results["historical"] = await test_historical_request()
    results["concurrent"] = await test_concurrent_requests()

    # kcat info
    show_kcat_info()

    # Summary
    print_separator("Results")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = " PASS" if ok else " FAIL"
        print(f"  {status}  {name}")
    print(f"\n  {passed}/{total} passed")

    if passed < total:
        print("\n  Some tests failed. Ensure ingestion service is running:")
        print("    cd ../ingestion && python main.py")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
