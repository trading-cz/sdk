"""Unit tests for RequestReply."""
# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import DataRequestType
from tradingcz.sdk.models.events import DataReady, DataRequest
from tradingcz.sdk.transport.kafka_settings import KafkaSettings


@pytest.mark.asyncio
async def test_reply_arriving_during_send_is_not_lost() -> None:
    rr = RequestReply(MagicMock(), KafkaSettings(consumer_group="t"), "svc", "rr", response_types=[DataReady])
    rr._typed_producer.send = AsyncMock(side_effect=lambda _req, key, headers: rr._pending[headers.event_id].set_result("reply"))
    rr._typed_producer.flush = AsyncMock()

    request = DataRequest(type=DataRequestType.HISTORIC, symbols=["SPY"])
    assert await rr.request(request, response_type=DataReady, timeout=1) == "reply"
