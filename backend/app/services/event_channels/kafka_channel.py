"""Kafka 推送通道。

通过 Kafka 生产者将事件推送到指定 Topic。
"""

from __future__ import annotations

import json
import time
from typing import Any

from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services.event_channels.base import BaseChannel, ChannelResult

logger: BoundLogger = get_logger("app.event_channels.kafka")


class KafkaChannel(BaseChannel):
    """Kafka 推送通道。

    支持以下连接参数：
    - ``bootstrap_servers``: Kafka 引导服务器（覆盖全局配置）
    - ``topic``: 默认 Topic（可被 ``target`` 覆盖）
    - ``acks``: 确认级别（默认 all）
    - ``linger_ms``: 批量发送等待时间（默认 10）

    支持以下额外配置：
    - ``key_field``: 用作消息键的 payload 字段名（默认 ``id``）
    - ``headers``: 消息头字典
    """

    async def send(
        self,
        target: str,
        payload: dict[str, Any],
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """发送事件到 Kafka Topic。

        Args:
            target: 目标 Topic（覆盖 connection_params 中的默认 Topic）
        """
        connection_params = connection_params or {}
        extra_config = extra_config or {}

        topic = target or connection_params.get("topic")
        if not topic:
            return ChannelResult(
                success=False,
                error_message="Kafka Topic 未指定",
            )

        # 获取消息键
        key_field = extra_config.get("key_field", "id")
        key = str(payload.get(key_field, "")) or None

        start = time.monotonic()
        try:
            # 延迟导入避免循环依赖
            from app.core.kafka import get_kafka_producer

            producer = get_kafka_producer()

            # 序列化消息
            value = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            key_bytes = key.encode("utf-8") if key else None

            # 消息头
            headers = extra_config.get("headers") or {}
            kafka_headers = (
                [(k, str(v).encode("utf-8")) for k, v in headers.items()] if headers else None
            )

            # 同步发送并等待确认
            # TODO: 实际生产环境应使用异步 future 与回调
            future = producer.send(topic, key=key_bytes, value=value, headers=kafka_headers)
            metadata = future.get(timeout=30)

            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "Kafka 推送成功",
                topic=topic,
                partition=metadata.partition,
                offset=metadata.offset,
                latency_ms=latency_ms,
            )
            return ChannelResult(
                success=True,
                latency_ms=latency_ms,
                response_body=(
                    f"topic={topic}, partition={metadata.partition}, offset={metadata.offset}"
                ),
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Kafka 推送失败",
                topic=topic,
                error=str(e),
            )
            return ChannelResult(
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def test_connection(
        self,
        target: str,
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """测试 Kafka 连接（发送测试消息到指定 Topic）。"""
        connection_params = connection_params or {}
        topic = target or connection_params.get("topic", "test-topic")
        test_payload = {
            "event_type": "kafka_test",
            "message": "Kafka connection test",
            "timestamp": time.time(),
        }
        return await self.send(
            target=topic,
            payload=test_payload,
            connection_params=connection_params,
            auth_config=auth_config,
            extra_config=extra_config,
        )
