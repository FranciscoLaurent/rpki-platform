"""事件推送服务。

统一事件推送入口，支持 Webhook、Syslog、Kafka 三种通道，
按集成配置分发事件并记录投递结果。复用 ``app.services.event_channels``
中已实现的通道类，向上提供函数式接口。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.models.integration import EventDelivery, EventSubscription, IntegrationConfig
from app.services.event_channels import KafkaChannel, SyslogChannel, WebhookChannel

logger: BoundLogger = get_logger("app.event_publisher")

# 通道类型到通道实现的映射
_CHANNEL_REGISTRY: dict[str, Any] = {
    "webhook": WebhookChannel(),
    "syslog": SyslogChannel(),
    "kafka": KafkaChannel(),
}


async def publish_webhook(config: dict[str, Any], event: dict[str, Any]) -> bool:
    """通过 Webhook 推送事件。

    Args:
        config: Webhook 配置，需包含 ``url``，可选 ``secret``、``headers``、
            ``timeout``、``verify_tls``、``sign_algorithm``、``sign_field``。
        event: 事件内容。

    Returns:
        是否推送成功。
    """
    url = config.get("url")
    if not url:
        logger.error("Webhook 推送失败：URL 未配置")
        return False

    channel: WebhookChannel = _CHANNEL_REGISTRY["webhook"]
    # 构造通道所需的连接参数、认证信息与额外配置
    connection_params = {
        "timeout": config.get("timeout", 10),
        "verify_tls": config.get("verify_tls", True),
    }
    auth_config: dict[str, Any] = {}
    if config.get("secret"):
        auth_config = {
            "type": "hmac",
            "secret": config["secret"],
        }
    extra_config: dict[str, Any] = {
        "headers": config.get("headers") or {},
        "sign_algorithm": config.get("sign_algorithm", "sha256"),
        "sign_field": config.get("sign_field", "X-Signature"),
    }

    result = await channel.send(
        target=url,
        payload=event,
        connection_params=connection_params,
        auth_config=auth_config,
        extra_config=extra_config,
    )
    if not result.success:
        logger.error(
            "Webhook 推送失败",
            url=url,
            error=result.error_message,
            status_code=result.status_code,
        )
    return result.success


async def publish_syslog(config: dict[str, Any], event: dict[str, Any]) -> bool:
    """通过 Syslog 推送事件（RFC 5424）。

    Args:
        config: Syslog 配置，需包含 ``host``，可选 ``port``、``protocol``、
            ``facility``、``app_name``、``timeout``。
        event: 事件内容。

    Returns:
        是否推送成功。
    """
    host = config.get("host")
    if not host:
        logger.error("Syslog 推送失败：主机地址未配置")
        return False

    channel: SyslogChannel = _CHANNEL_REGISTRY["syslog"]
    connection_params = {
        "host": host,
        "port": int(config.get("port", 514)),
        "protocol": config.get("protocol", "udp"),
        "facility": config.get("facility", "local0"),
        "app_name": config.get("app_name", "rpki-platform"),
        "timeout": config.get("timeout", 5),
    }

    result = await channel.send(
        target=f"{host}:{connection_params['port']}",
        payload=event,
        connection_params=connection_params,
    )
    if not result.success:
        logger.error(
            "Syslog 推送失败",
            host=host,
            port=connection_params["port"],
            error=result.error_message,
        )
    return result.success


async def publish_kafka(config: dict[str, Any], event: dict[str, Any]) -> bool:
    """通过 Kafka 推送事件。

    复用 ``app.core.kafka`` 中的全局生产者。

    Args:
        config: Kafka 配置，需包含 ``topic``，可选 ``bootstrap_servers``、
            ``acks``、``key_field``。
        event: 事件内容。

    Returns:
        是否推送成功。
    """
    topic = config.get("topic")
    if not topic:
        logger.error("Kafka 推送失败：Topic 未配置")
        return False

    channel: KafkaChannel = _CHANNEL_REGISTRY["kafka"]
    connection_params: dict[str, Any] = {
        "topic": topic,
    }
    if config.get("bootstrap_servers"):
        connection_params["bootstrap_servers"] = config["bootstrap_servers"]
    if config.get("acks"):
        connection_params["acks"] = config["acks"]
    extra_config: dict[str, Any] = {
        "key_field": config.get("key_field", "id"),
    }

    result = await channel.send(
        target=topic,
        payload=event,
        connection_params=connection_params,
        extra_config=extra_config,
    )
    if not result.success:
        logger.error(
            "Kafka 推送失败",
            topic=topic,
            error=result.error_message,
        )
    return result.success


# 通道类型到推送函数的映射
_PUBLISH_FUNCS = {
    "webhook": publish_webhook,
    "syslog": publish_syslog,
    "kafka": publish_kafka,
}


async def publish_event(
    db: AsyncSession,
    event_type: str,
    event_data: dict[str, Any],
    channels: list[str],
) -> dict[str, Any]:
    """统一事件推送入口，按配置分发到各通道。

    遍历指定的通道列表，从数据库查询对应类型的已启用集成配置，
    将事件分发到所有匹配的通道，并记录投递结果。

    Args:
        db: 数据库会话。
        event_type: 事件类型（如 ``alert.created``、``incident.updated``）。
        event_data: 事件数据。
        channels: 通道类型列表（如 ``["webhook", "kafka"]``）。

    Returns:
        推送结果汇总，包含每个通道的成功/失败计数与详情。
    """
    # 构造完整事件 payload
    payload: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": event_data,
    }
    # 若事件数据中包含 id，提升到顶层用作消息键
    if "id" in event_data:
        payload["id"] = event_data["id"]

    results: dict[str, Any] = {
        "event_type": event_type,
        "channels": {},
        "total_success": 0,
        "total_failure": 0,
    }

    for channel_type in channels:
        publish_func = _PUBLISH_FUNCS.get(channel_type)
        if publish_func is None:
            logger.warning("不支持的通道类型", channel_type=channel_type)
            results["channels"][channel_type] = {
                "success": False,
                "error": f"不支持的通道类型: {channel_type}",
            }
            results["total_failure"] += 1
            continue

        # 查询该通道类型的已启用集成配置
        stmt = select(IntegrationConfig).where(
            IntegrationConfig.integration_type == channel_type,
            IntegrationConfig.enabled.is_(True),
        )
        db_result = await db.execute(stmt)
        configs = db_result.scalars().all()

        if not configs:
            logger.info(
                "未找到已启用的通道配置",
                channel_type=channel_type,
            )
            results["channels"][channel_type] = {
                "success": True,
                "message": "无已配置的通道",
                "deliveries": [],
            }
            continue

        channel_deliveries: list[dict[str, Any]] = []
        channel_success = 0
        channel_failure = 0

        for integration in configs:
            # 合并连接参数、认证信息与额外配置为单一 config 字典
            merged_config: dict[str, Any] = {}
            if integration.connection_params:
                merged_config.update(integration.connection_params)
            if integration.auth_config:
                merged_config.update(integration.auth_config)
            if integration.extra_config:
                merged_config.update(integration.extra_config)

            start = time.monotonic()
            try:
                success = await publish_func(merged_config, payload)
                latency_ms = int((time.monotonic() - start) * 1000)
            except Exception as e:
                logger.error(
                    "事件推送异常",
                    channel_type=channel_type,
                    integration_id=integration.id,
                    error=str(e),
                )
                success = False
                latency_ms = int((time.monotonic() - start) * 1000)

            delivery_record = {
                "integration_id": integration.id,
                "integration_name": integration.name,
                "success": success,
                "latency_ms": latency_ms,
            }

            # 记录投递日志到数据库
            await _record_delivery(
                db=db,
                integration=integration,
                event_type=event_type,
                payload=payload,
                success=success,
                latency_ms=latency_ms,
            )

            if success:
                channel_success += 1
                results["total_success"] += 1
            else:
                channel_failure += 1
                results["total_failure"] += 1

            channel_deliveries.append(delivery_record)

        results["channels"][channel_type] = {
            "success": channel_failure == 0,
            "success_count": channel_success,
            "failure_count": channel_failure,
            "deliveries": channel_deliveries,
        }

    logger.info(
        "事件推送完成",
        event_type=event_type,
        total_success=results["total_success"],
        total_failure=results["total_failure"],
    )
    return results


async def _record_delivery(
    db: AsyncSession,
    integration: IntegrationConfig,
    event_type: str,
    payload: dict[str, Any],
    success: bool,
    latency_ms: int,
) -> None:
    """记录事件投递结果到数据库。

    将每次投递记录为一条 EventDelivery，便于审计与重试。
    若记录失败仅记录日志，不影响主流程。
    """
    try:
        # 查找该集成的订阅（取第一条匹配的）
        stmt = (
            select(EventSubscription)
            .where(
                EventSubscription.integration_id == integration.id,
                EventSubscription.enabled.is_(True),
            )
            .limit(1)
        )
        sub_result = await db.execute(stmt)
        subscription = sub_result.scalar_one_or_none()

        delivery = EventDelivery(
            subscription_id=subscription.id if subscription else 0,
            event_type=event_type,
            resource_type=payload.get("data", {}).get("resource_type"),
            resource_id=str(payload.get("data", {}).get("resource_id", "")),
            payload=payload,
            status="success" if success else "failed",
            retry_count=0,
            last_attempt_at=datetime.now(UTC),
            response_status_code=200 if success else None,
            error_message=None if success else "推送失败",
        )
        db.add(delivery)
        await db.flush()
    except Exception as e:
        logger.warning(
            "记录投递日志失败",
            integration_id=integration.id,
            error=str(e),
        )


async def list_push_channels(db: AsyncSession) -> list[dict[str, Any]]:
    """列出已配置的推送通道。

    查询所有 Webhook、Syslog、Kafka 类型的集成配置，返回通道概要信息。

    Args:
        db: 数据库会话。

    Returns:
        通道列表，每项包含 id、name、type、enabled、status 等字段。
    """
    stmt = (
        select(IntegrationConfig)
        .where(IntegrationConfig.integration_type.in_(["webhook", "syslog", "kafka"]))
        .order_by(IntegrationConfig.integration_type, IntegrationConfig.name)
    )
    result = await db.execute(stmt)
    integrations = result.scalars().all()

    channels: list[dict[str, Any]] = []
    for integration in integrations:
        channels.append(
            {
                "id": integration.id,
                "name": integration.name,
                "type": integration.integration_type,
                "subtype": integration.subtype,
                "enabled": integration.enabled,
                "status": integration.last_test_status or "unknown",
                "last_test_at": (
                    integration.last_test_at.isoformat() if integration.last_test_at else None
                ),
                "tenant_id": integration.tenant_id,
            }
        )
    return channels


async def test_channel(channel_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """测试通道连通性。

    向指定通道发送一条测试事件，验证连通性。

    Args:
        channel_type: 通道类型（webhook/syslog/kafka）。
        config: 通道配置。

    Returns:
        测试结果，包含 success、message、latency_ms 字段。
    """
    publish_func = _PUBLISH_FUNCS.get(channel_type)
    if publish_func is None:
        return {
            "success": False,
            "message": f"不支持的通道类型: {channel_type}",
            "latency_ms": None,
        }

    test_event = {
        "id": f"test-{int(time.time())}",
        "event_type": "channel.test",
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": "P4",
        "message": "通道连通性测试",
        "data": {"test": True},
    }

    start = time.monotonic()
    try:
        success = await publish_func(config, test_event)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "success": success,
            "message": "通道连通性测试成功" if success else "通道连通性测试失败",
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "success": False,
            "message": f"通道测试异常: {e}",
            "latency_ms": latency_ms,
        }


__all__ = [
    "list_push_channels",
    "publish_event",
    "publish_kafka",
    "publish_syslog",
    "publish_webhook",
    "test_channel",
]
