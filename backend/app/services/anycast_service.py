"""Anycast 节点管理服务。

提供 Anycast 节点的 CRUD 与节点检查能力。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.benign_conflict import AnycastNode
from app.schemas.benign_conflict import (
    AnycastNodeCreate,
    AnycastNodeUpdate,
)

logger = get_logger("app.anycast_service")


async def create_anycast_node(db: AsyncSession, node_data: AnycastNodeCreate) -> AnycastNode:
    """创建 Anycast 节点。

    Args:
        db: 异步数据库会话
        node_data: Anycast 节点创建数据

    Returns:
        创建后的 Anycast 节点对象
    """
    node = AnycastNode(
        node_asn=node_data.node_asn,
        prefix=node_data.prefix,
        region=node_data.region,
        site=node_data.site,
        business_tag=node_data.business_tag,
        registered_at=node_data.registered_at,
        status=node_data.status,
        tenant_id=node_data.tenant_id,
    )
    db.add(node)
    await db.flush()
    await db.commit()
    await db.refresh(node)

    logger.info(
        "Anycast 节点已创建",
        node_id=node.id,
        node_asn=node.node_asn,
        prefix=node.prefix,
    )
    return node


async def get_anycast_node(db: AsyncSession, node_id: int) -> AnycastNode | None:
    """根据 ID 获取 Anycast 节点。"""
    stmt = select(AnycastNode).where(AnycastNode.id == node_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_anycast_nodes(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[AnycastNode]:
    """分页查询 Anycast 节点。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``node_asn``、``prefix``、``status``、``region``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        Anycast 节点列表
    """
    stmt = select(AnycastNode)
    if filters:
        if filters.get("node_asn") is not None:
            stmt = stmt.where(AnycastNode.node_asn == filters["node_asn"])
        if filters.get("prefix"):
            stmt = stmt.where(AnycastNode.prefix == filters["prefix"])
        if filters.get("status"):
            stmt = stmt.where(AnycastNode.status == filters["status"])
        if filters.get("region"):
            stmt = stmt.where(AnycastNode.region == filters["region"])

    stmt = stmt.order_by(AnycastNode.registered_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_anycast_nodes(db: AsyncSession, filters: dict[str, Any] | None = None) -> int:
    """统计 Anycast 节点数量。"""
    stmt = select(func.count(AnycastNode.id))
    if filters:
        if filters.get("node_asn") is not None:
            stmt = stmt.where(AnycastNode.node_asn == filters["node_asn"])
        if filters.get("prefix"):
            stmt = stmt.where(AnycastNode.prefix == filters["prefix"])
        if filters.get("status"):
            stmt = stmt.where(AnycastNode.status == filters["status"])
        if filters.get("region"):
            stmt = stmt.where(AnycastNode.region == filters["region"])

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_anycast_node(
    db: AsyncSession,
    node: AnycastNode,
    node_update: AnycastNodeUpdate,
) -> AnycastNode:
    """更新 Anycast 节点。

    Args:
        db: 异步数据库会话
        node: 待更新的 Anycast 节点对象
        node_update: 更新数据

    Returns:
        更新后的 Anycast 节点对象
    """
    update_data = node_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(node, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(node)

    logger.info(
        "Anycast 节点已更新",
        node_id=node.id,
    )
    return node


async def delete_anycast_node(db: AsyncSession, node: AnycastNode) -> None:
    """删除 Anycast 节点。"""
    await db.delete(node)
    await db.commit()

    logger.info(
        "Anycast 节点已删除",
        node_id=node.id,
    )


async def check_anycast_node(
    db: AsyncSession,
    asn: int,
    prefix: str,
) -> AnycastNode | None:
    """检查是否为已登记的 Anycast 节点。

    匹配条件：
    - 节点 AS 号匹配
    - 前缀匹配
    - 状态为 active

    Args:
        db: 异步数据库会话
        asn: Anycast 节点 AS 号
        prefix: Anycast 前缀

    Returns:
        匹配的 Anycast 节点对象，无匹配返回 None
    """
    stmt = (
        select(AnycastNode)
        .where(AnycastNode.node_asn == asn)
        .where(AnycastNode.prefix == prefix)
        .where(AnycastNode.status == "active")
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


__all__ = [
    "check_anycast_node",
    "count_anycast_nodes",
    "create_anycast_node",
    "delete_anycast_node",
    "get_anycast_node",
    "get_anycast_nodes",
    "update_anycast_node",
]
