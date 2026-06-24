"""Kafka 生产者与消费者基础组件。

提供全局 Kafka 生产者管理、事件发送服务以及消费者基类。
生产者使用同步 API（kafka-python），消费者提供异步处理接口。
"""

from __future__ import annotations

import abc
import asyncio
import json
from typing import Any, ClassVar

from kafka import KafkaConsumer, KafkaProducer
from structlog.stdlib import BoundLogger

from app.core.config import settings
from app.core.logging import get_logger

logger: BoundLogger = get_logger("app.kafka")


class Topics:
    """Kafka 主题常量定义。

    所有业务模块统一使用此处定义的主题名称，避免硬编码。
    """

    # BGP 事件主题：路由异常、泄露、劫持等
    BGP_EVENTS: ClassVar[str] = "bgp-events"
    # RPKI 事件主题：VRP 变更、ROA 验证等
    RPKI_EVENTS: ClassVar[str] = "rpki-events"
    # 告警事件主题：安全告警、阈值触发等
    ALERT_EVENTS: ClassVar[str] = "alert-events"
    # 审计事件主题：用户操作、系统变更等
    AUDIT_EVENTS: ClassVar[str] = "audit-events"


# 全局 Kafka 生产者单例
_producer: KafkaProducer | None = None


def _value_serializer(value: Any) -> bytes:
    """将字典序列化为 JSON 字节串。"""
    return json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")


def _key_serializer(key: str | None) -> bytes | None:
    """将字符串键序列化为字节串。"""
    if key is None:
        return None
    return key.encode("utf-8")


def init_kafka_producer() -> None:
    """初始化全局 Kafka 生产者。

    在应用启动时调用，连接失败会记录日志并抛出异常。
    """
    global _producer
    try:
        _producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=_value_serializer,
            key_serializer=_key_serializer,
            acks="all",
            retries=3,
            linger_ms=10,
        )
        logger.info(
            "Kafka 生产者初始化成功",
            servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
    except Exception as e:
        logger.error(
            "Kafka 生产者初始化失败",
            servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            error=str(e),
        )
        _producer = None
        raise


def close_kafka_producer() -> None:
    """关闭全局 Kafka 生产者。

    在应用关闭时调用，刷新缓冲区并释放资源。
    """
    global _producer
    if _producer is not None:
        _producer.flush()
        _producer.close()
        _producer = None
        logger.info("Kafka 生产者已关闭")


def get_kafka_producer() -> KafkaProducer:
    """获取全局 Kafka 生产者实例。

    Returns:
        KafkaProducer 实例

    Raises:
        RuntimeError: 生产者未初始化
    """
    if _producer is None:
        raise RuntimeError("Kafka 生产者未初始化，请先调用 init_kafka_producer()")
    return _producer


def _on_send_error(excp: BaseException) -> None:
    """Kafka 消息发送失败的错误回调。"""
    logger.error("Kafka 消息发送失败", error=str(excp))


class KafkaService:
    """Kafka 生产者服务，封装事件发送功能。

    提供单条与批量事件发送，自动处理 JSON 序列化。
    """

    def __init__(self, producer: KafkaProducer) -> None:
        self._producer = producer

    def send_event(
        self,
        topic: str,
        key: str | None,
        value: dict[str, Any],
    ) -> None:
        """发送单个事件到指定主题。

        Args:
            topic: 目标主题
            key: 分区键（可为 None）
            value: 事件内容（字典，自动 JSON 序列化）
        """
        future = self._producer.send(topic, key=key, value=value)
        future.add_errback(_on_send_error)

    def send_events(
        self,
        topic: str,
        events: list[dict[str, Any]],
    ) -> None:
        """批量发送事件到指定主题。

        发送完成后统一 flush，确保所有消息已写入 Kafka。

        Args:
            topic: 目标主题
            events: 事件列表（每个元素为字典）
        """
        for event in events:
            key = str(event.get("id", ""))
            self._producer.send(topic, key=key, value=event)
        self._producer.flush()


class BaseConsumer(abc.ABC):
    """Kafka 消费者基类。

    子类需实现 ``process_message`` 方法处理消息。
    消费者使用 kafka-python 的同步 KafkaConsumer，但提供异步消费循环，
    通过 ``asyncio.to_thread`` 将阻塞的 poll 操作放入线程池执行。
    """

    def __init__(
        self,
        topic: str,
        group_id: str,
        bootstrap_servers: str | None = None,
    ) -> None:
        self._topic = topic
        self._group_id = group_id
        self._bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self._consumer: KafkaConsumer[Any, Any] | None = None
        self._running = False
        self._logger: BoundLogger = get_logger(f"app.kafka.consumer.{group_id}")

    def start(self) -> None:
        """创建 KafkaConsumer 实例并开始消费准备。"""
        self._consumer = KafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=_deserialize_value,
            key_deserializer=_deserialize_key,
        )
        self._running = True
        self._logger.info(
            "Kafka 消费者已启动",
            topic=self._topic,
            group_id=self._group_id,
        )

    async def consume(self) -> None:
        """异步消费消息循环。

        在后台任务中运行，通过线程池执行阻塞的 poll 操作，
        每条消息异步调用 ``process_message`` 处理。
        """
        if self._consumer is None:
            raise RuntimeError("消费者未启动，请先调用 start()")

        while self._running:
            # 在线程池中执行阻塞的 poll，避免阻塞事件循环
            records = await asyncio.to_thread(self._consumer.poll, 1.0)
            if not records:
                continue

            for messages in records.values():
                for record in messages:
                    try:
                        await self.process_message(record.value)
                        # 处理成功后提交偏移量
                        await asyncio.to_thread(self._consumer.commit)
                    except Exception as e:
                        self._logger.error(
                            "消息处理失败",
                            topic=record.topic,
                            partition=record.partition,
                            offset=record.offset,
                            error=str(e),
                        )

    @abc.abstractmethod
    async def process_message(self, message: dict[str, Any]) -> None:
        """处理消息的抽象方法，子类必须实现。

        Args:
            message: 消息内容（已反序列化为字典）
        """
        ...

    def stop(self) -> None:
        """停止消费者，释放资源。"""
        self._running = False
        if self._consumer is not None:
            self._consumer.close()
            self._consumer = None
            self._logger.info("Kafka 消费者已停止")


def _deserialize_value(value: bytes | None) -> dict[str, Any] | None:
    """将字节串反序列化为字典。"""
    if value is None:
        return None
    return json.loads(value.decode("utf-8"))


def _deserialize_key(key: bytes | None) -> str | None:
    """将字节串反序列化为字符串键。"""
    if key is None:
        return None
    return key.decode("utf-8")
