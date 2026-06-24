"""维护窗口管理服务。

提供维护窗口的 CRUD 与活跃维护窗口检查能力。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.benign_conflict import MaintenanceWindow
from app.schemas.benign_conflict import (
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
)

logger = get_logger("app.maintenance_service")


async def create_maintenance_window(
    db: AsyncSession, window_data: MaintenanceWindowCreate
) -> MaintenanceWindow:
    """创建维护窗口。

    Args:
        db: 异步数据库会话
        window_data: 维护窗口创建数据

    Returns:
        创建后的维护窗口对象
    """
    window = MaintenanceWindow(
        name=window_data.name,
        description=window_data.description,
        start_time=window_data.start_time,
        end_time=window_data.end_time,
        prefixes=window_data.prefixes,
        asns=window_data.asns,
        approved_by=window_data.approved_by,
        status=window_data.status,
        work_order_id=window_data.work_order_id,
        tenant_id=window_data.tenant_id,
    )
    db.add(window)
    await db.flush()
    await db.commit()
    await db.refresh(window)

    logger.info(
        "维护窗口已创建",
        window_id=window.id,
        name=window.name,
    )
    return window


async def get_maintenance_window(db: AsyncSession, window_id: int) -> MaintenanceWindow | None:
    """根据 ID 获取维护窗口。"""
    stmt = select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_maintenance_windows(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[MaintenanceWindow]:
    """分页查询维护窗口。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``status``、``work_order_id``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        维护窗口列表
    """
    stmt = select(MaintenanceWindow)
    if filters:
        if filters.get("status"):
            stmt = stmt.where(MaintenanceWindow.status == filters["status"])
        if filters.get("work_order_id"):
            stmt = stmt.where(MaintenanceWindow.work_order_id == filters["work_order_id"])

    stmt = stmt.order_by(MaintenanceWindow.start_time.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_maintenance_windows(db: AsyncSession, filters: dict[str, Any] | None = None) -> int:
    """统计维护窗口数量。"""
    stmt = select(func.count(MaintenanceWindow.id))
    if filters:
        if filters.get("status"):
            stmt = stmt.where(MaintenanceWindow.status == filters["status"])
        if filters.get("work_order_id"):
            stmt = stmt.where(MaintenanceWindow.work_order_id == filters["work_order_id"])

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_maintenance_window(
    db: AsyncSession,
    window: MaintenanceWindow,
    window_update: MaintenanceWindowUpdate,
) -> MaintenanceWindow:
    """更新维护窗口。

    Args:
        db: 异步数据库会话
        window: 待更新的维护窗口对象
        window_update: 更新数据

    Returns:
        更新后的维护窗口对象
    """
    update_data = window_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(window, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(window)

    logger.info(
        "维护窗口已更新",
        window_id=window.id,
    )
    return window


async def delete_maintenance_window(db: AsyncSession, window: MaintenanceWindow) -> None:
    """删除维护窗口。"""
    await db.delete(window)
    await db.commit()

    logger.info(
        "维护窗口已删除",
        window_id=window.id,
    )


async def check_active_maintenance(
    db: AsyncSession,
    prefix: str,
    asn: int | None = None,
    at_time: datetime | None = None,
) -> MaintenanceWindow | None:
    """检查是否有活跃的维护窗口。

    匹配条件：
    - 指定时间在窗口时间范围内（默认为当前时间）
    - 窗口状态为 scheduled 或 active
    - 前缀在窗口的受影响前缀列表中，或 ASN 在受影响 ASN 列表中

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        asn: 起源 AS 号（可选）
        at_time: 检查时间点（默认为当前时间）

    Returns:
        匹配的维护窗口对象，无匹配返回 None
    """
    check_time = at_time or datetime.now(UTC)

    stmt = (
        select(MaintenanceWindow)
        .where(MaintenanceWindow.status.in_(["scheduled", "active"]))
        .where(MaintenanceWindow.start_time <= check_time)
        .where(MaintenanceWindow.end_time >= check_time)
        .order_by(MaintenanceWindow.start_time.desc())
    )
    result = await db.execute(stmt)
    windows = list(result.scalars().all())

    for window in windows:
        # 检查前缀匹配
        if window.prefixes and prefix in window.prefixes:
            return window
        # 检查 ASN 匹配
        if window.asns and asn is not None and asn in window.asns:
            return window
        # 若窗口未指定前缀和 ASN，视为全局匹配
        if not window.prefixes and not window.asns:
            return window

    return None


__all__ = [
    "check_active_maintenance",
    "count_maintenance_windows",
    "create_maintenance_window",
    "delete_maintenance_window",
    "get_maintenance_window",
    "get_maintenance_windows",
    "update_maintenance_window",
]
