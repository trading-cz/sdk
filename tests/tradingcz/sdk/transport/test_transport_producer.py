"""Unit tests for TransportProducer."""
# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

import pytest

from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.transport_producer import TransportProducer


def _producer(**kwargs: object) -> TransportProducer:
    with patch("tradingcz.sdk.transport.transport_producer.SyncProducer"):
        return TransportProducer(KafkaSettings(consumer_group="t"), **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_send_serves_delivery_reports() -> None:
    producer = _producer()
    await producer.send("topic", b"x", key="k")
    producer._producer.produce.assert_called_once()
    producer._producer.poll.assert_called_once_with(0)


def test_delivery_failure_reports_partition_and_offset_zero() -> None:
    on_error = MagicMock()
    producer = _producer(on_error=on_error)
    msg = MagicMock()
    msg.topic.return_value = "topic"
    msg.partition.return_value = 0
    msg.offset.return_value = 0
    producer._handle_error("boom", msg)
    on_error.assert_called_once_with("topic", 0, 0, "boom")
