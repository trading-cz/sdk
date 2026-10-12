"""Unit tests for KafkaTopicAdmin topic creation."""
# pylint: disable=protected-access

from concurrent.futures import Future
from unittest.mock import MagicMock

import pytest

from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicConfig


def _admin(settings: KafkaSettings) -> tuple[KafkaTopicAdmin, MagicMock]:
    created: Future[None] = Future()
    created.set_result(None)
    client = MagicMock()
    client.list_topics.return_value = MagicMock(topics={})
    client.create_topics.side_effect = lambda topics: {topic.topic: created for topic in topics}
    admin = KafkaTopicAdmin(settings)
    admin._admin = client
    return admin, client


@pytest.mark.asyncio
async def test_new_topic_uses_the_broker_default_replication_factor() -> None:
    admin, client = _admin(KafkaSettings(consumer_group="t"))
    await admin.ensure_from_config(KafkaTopicConfig(name="dev-event", partitions=1))
    (new_topic,) = client.create_topics.call_args.args[0]
    assert new_topic.replication_factor == -1


@pytest.mark.asyncio
async def test_configured_replication_factor_is_used() -> None:
    admin, client = _admin(KafkaSettings(consumer_group="t", default_replication_factor=1))
    await admin.ensure("dev-stock-stream-quotes")
    (new_topic,) = client.create_topics.call_args.args[0]
    assert new_topic.replication_factor == 1
