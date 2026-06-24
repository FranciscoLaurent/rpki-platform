"""集成配置管理服务。

提供集成配置的 CRUD 操作与连通性测试能力，统一管理所有外部集成的
连接信息与认证凭据。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.models.integration import IntegrationConfig
from app.services.integrations.base import BaseAdapter
from app.services.integrations.ipam_adapter import IPAMAdapter
from app.services.integrations.nms_adapter import NMSAdapter
from app.services.integrations.notification_adapter import CollaborationAdapter
from app.services.integrations.siem_adapter import ITSMAdapter, SIEMAdapter
from app.services.integrations.external_info import RIRAdapter

logger: BoundLogger = get_logger("app.integration_config_service")


# 集成类型到适配器类的映射
_ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "ipam": IPAMAdapter,
    "siem": SIEMAdapter,
    "nms": NMSAdapter,
    "rir": RIRAdapter,
    "collaboration": CollaborationAdapter,
}


async def list_integrations(db: AsyncSession) -> list[dict[str, Any]]:
    """列出所有集成配置。

    Args:
        db: 数据库会话。

    Returns:
        集成配置列表。
    """
    stmt = select(IntegrationConfig).order_by(
        IntegrationConfig.integration_type, IntegrationConfig.name
    )
    result = await db.execute(stmt)
    integrations = result.scalars().all()
    return [_integration_to_dict(i) for i in integrations]


async def get_integration(
    db: AsyncSession, integration_id: int
) -> dict[str, Any] | None:
    """获取集成配置。

    Args:
        db: 数据库会话。
        integration_id: 集成配置 ID。

    Returns:
        集成配置字典，不存在则返回 None。
    """
    stmt = select(IntegrationConfig).where(IntegrationConfig.id == integration_id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()
    if integration is None:
        return None
    return _integration_to_dict(integration)


async def create_integration(
    db: AsyncSession, config: dict[str, Any]
) -> dict[str, Any]:
    """创建集成配置。

    Args:
        db: 数据库会话。
        config: 集成配置数据，需包含 name、code、integration_type。

    Returns:
        创建后的集成配置字典。

    Raises:
        ValueError: 编码已存在。
    """
    # 检查 code 唯一性
    code = config.get("code")
    if code:
        stmt = select(IntegrationConfig).where(IntegrationConfig.code == code)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise ValueError(f"集成编码 {code} 已存在")

    integration = IntegrationConfig(
        name=config["name"],
        code=config.get("code", f"integration-{int(datetime.now(timezone.utc).timestamp())}"),
        description=config.get("description"),
        integration_type=config["integration_type"],
        subtype=config.get("subtype"),
        connection_params=config.get("connection_params"),
        auth_config=config.get("auth_config"),
        extra_config=config.get("extra_config"),
        enabled=config.get("enabled", True),
        tenant_id=config.get("tenant_id"),
    )
    db.add(integration)
    await db.flush()
    await db.refresh(integration)
    logger.info(
        "集成配置已创建",
        integration_id=integration.id,
        name=integration.name,
        type=integration.integration_type,
    )
    return _integration_to_dict(integration)


async def update_integration(
    db: AsyncSession, integration_id: int, config: dict[str, Any]
) -> dict[str, Any] | None:
    """更新集成配置。

    Args:
        db: 数据库会话。
        integration_id: 集成配置 ID。
        config: 更新数据。

    Returns:
        更新后的集成配置字典，不存在则返回 None。
    """
    stmt = select(IntegrationConfig).where(IntegrationConfig.id == integration_id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()
    if integration is None:
        return None

    # 更新字段
    if "name" in config:
        integration.name = config["name"]
    if "description" in config:
        integration.description = config["description"]
    if "integration_type" in config:
        integration.integration_type = config["integration_type"]
    if "subtype" in config:
        integration.subtype = config["subtype"]
    if "connection_params" in config:
        integration.connection_params = config["connection_params"]
    if "auth_config" in config:
        integration.auth_config = config["auth_config"]
    if "extra_config" in config:
        integration.extra_config = config["extra_config"]
    if "enabled" in config:
        integration.enabled = config["enabled"]

    await db.flush()
    await db.refresh(integration)
    logger.info(
        "集成配置已更新",
        integration_id=integration.id,
        name=integration.name,
    )
    return _integration_to_dict(integration)


async def delete_integration(
    db: AsyncSession, integration_id: int
) -> bool:
    """删除集成配置。

    Args:
        db: 数据库会话。
        integration_id: 集成配置 ID。

    Returns:
        是否删除成功（不存在则返回 False）。
    """
    stmt = select(IntegrationConfig).where(IntegrationConfig.id == integration_id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()
    if integration is None:
        return False

    await db.delete(integration)
    await db.flush()
    logger.info(
        "集成配置已删除",
        integration_id=integration_id,
        name=integration.name,
    )
    return True


async def test_integration(
    db: AsyncSession, integration_id: int
) -> dict[str, Any]:
    """测试集成连通性。

    根据集成类型选择对应的适配器，调用 test_connection 方法测试连通性，
    并更新集成配置的测试状态字段。

    Args:
        db: 数据库会话。
        integration_id: 集成配置 ID。

    Returns:
        测试结果，包含 success、message、latency_ms 字段。
    """
    stmt = select(IntegrationConfig).where(IntegrationConfig.id == integration_id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()
    if integration is None:
        return {
            "success": False,
            "message": f"集成配置 {integration_id} 不存在",
            "latency_ms": None,
        }

    # 获取适配器类
    adapter_cls = _ADAPTER_MAP.get(integration.integration_type)
    if adapter_cls is None:
        # 对于 webhook/syslog/kafka 类型，使用事件推送通道测试
        return await _test_push_channel(integration)

    # 构造适配器实例
    adapter = adapter_cls(
        connection_params=integration.connection_params or {},
        auth_config=integration.auth_config or {},
        extra_config=integration.extra_config or {},
    )

    try:
        result = await adapter.test_connection()
        # 更新测试状态
        integration.last_test_status = "success" if result.success else "failed"
        integration.last_test_message = result.error_message or "测试成功"
        integration.last_test_at = datetime.now(timezone.utc)
        await db.flush()

        return {
            "success": result.success,
            "message": result.error_message or "连通性测试成功",
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        integration.last_test_status = "failed"
        integration.last_test_message = str(e)
        integration.last_test_at = datetime.now(timezone.utc)
        await db.flush()
        return {
            "success": False,
            "message": str(e),
            "latency_ms": None,
        }


async def _test_push_channel(integration: IntegrationConfig) -> dict[str, Any]:
    """测试事件推送通道（webhook/syslog/kafka）。"""
    from app.services.event_publisher import test_channel

    # 合并配置
    merged_config: dict[str, Any] = {}
    if integration.connection_params:
        merged_config.update(integration.connection_params)
    if integration.auth_config:
        merged_config.update(integration.auth_config)
    if integration.extra_config:
        merged_config.update(integration.extra_config)

    return await test_channel(integration.integration_type, merged_config)


def _integration_to_dict(integration: IntegrationConfig) -> dict[str, Any]:
    """将 IntegrationConfig 模型实例转换为字典。"""
    return {
        "id": integration.id,
        "name": integration.name,
        "code": integration.code,
        "description": integration.description,
        "integration_type": integration.integration_type,
        "subtype": integration.subtype,
        "connection_params": integration.connection_params,
        "auth_config": integration.auth_config,
        "extra_config": integration.extra_config,
        "enabled": integration.enabled,
        "last_test_status": integration.last_test_status,
        "last_test_message": integration.last_test_message,
        "last_test_at": integration.last_test_at.isoformat()
        if integration.last_test_at
        else None,
        "tenant_id": integration.tenant_id,
        "created_at": integration.created_at.isoformat()
        if integration.created_at
        else None,
        "updated_at": integration.updated_at.isoformat()
        if integration.updated_at
        else None,
    }


__all__ = [
    "create_integration",
    "delete_integration",
    "get_integration",
    "list_integrations",
    "test_integration",
    "update_integration",
]
