"""Kafka client utilities and helpers."""

from confluent_kafka.admin import AdminClient
from confluent_kafka.error import KafkaException


class KafkaHelper:
    @staticmethod
    def list_topics(bootstrap_servers: str) -> list[str]:
        try:
            conf = {"bootstrap.servers": bootstrap_servers}
            admin_client = AdminClient(conf)
            cluster_metadata = admin_client.list_topics(timeout=10)
            return list(cluster_metadata.topics.keys())
        except KafkaException as e:
            raise KafkaException(f"Failed to list Kafka topics: {str(e)}") from e

    @staticmethod
    def topic_exists(bootstrap_servers: str, topic_name: str) -> bool:
        try:
            topics = KafkaHelper.list_topics(bootstrap_servers)
            return topic_name in topics
        except KafkaException:
            return False

