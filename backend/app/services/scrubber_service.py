"""清洗商授权管理服务。

提供清洗商授权的 CRUD 与授权检查能力。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.benign_conflict import ScrubberAuthorization
from app.schemas.benign_conflict import (
    ScrubberAuthorizationCreate,
    ScrubberAuthorizationUpdate,
)

logger = get_logger("app.scrubber_service")


async def create_scrubber_authorization(
    db: AsyncSession, auth_data: ScrubberAuthorizationCreate
) -> ScrubberAuthorization:
    """创建清洗商授权。

    Args:
        db: 异步数据库会话
        auth_data: 清洗商授权创建数据

    Returns:
        创建后的清洗商授权对象
    """
    authorization = ScrubberAuthorization(
        scrubber_asn=auth_data.scrubber_asn,
        customer_prefix=auth_data.customer_prefix,
        customer_asn=auth_data.customer_asn,
        authorized_at=auth_data.authorized_at,
        expires_at=auth_data.expires_at,
        work_order_id=auth_data.work_order_id,
        status=auth_data.status,
        contact_info=auth_data.contact_info,
        tenant_id=auth_data.tenant_id,
    )
    db.add(authorization)
    await db.flush()
    await db.commit()
    await db.refresh(authorization)

    logger.info(
        "清洗商授权已创建",
        auth_id=authorization.id,
        scrubber_asn=authorization.scrubber_asn,
        customer_prefix=authorization.customer_prefix,
    )
    return authorization


async def get_scrubber_authorization(
    db: AsyncSession, auth_id: int
) -> ScrubberAuthorization | None:
    """根据 ID 获取清洗商授权。"""
    stmt = select(ScrubberAuthorization).where(
        ScrubberAuthorization.id == auth_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_scrubber_authorizations(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ScrubberAuthorization]:
    """分页查询清洗商授权。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``scrubber_asn``、``customer_asn``、``status``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        清洗商授权列表
    """
    stmt = select(ScrubberAuthorization)
    if filters:
        if filters.get("scrubber_asn") is not None:
            stmt = stmt.where(
                ScrubberAuthorization.scrubber_asn == filters["scrubber_asn"]
            )
        if filters.get("customer_asn") is not None:
            stmt = stmt.where(
                ScrubberAuthorization.customer_asn == filters["customer_asn"]
            )
        if filters.get("customer_prefix"):
            stmt = stmt.where(
                ScrubberAuthorization.customer_prefix == filters["customer_prefix"]
            )
        if filters.get("status"):
            stmt = stmt.where(ScrubberAuthorization.status == filters["status"])

    stmt = stmt.order_by(
        ScrubberAuthorization.authorized_at.desc()
    ).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_scrubber_authorizations(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计清洗商授权数量。"""
    stmt = select(func.count(ScrubberAuthorization.id))
    if filters:
        if filters.get("scrubber_asn") is not None:
            stmt = stmt.where(
                ScrubberAuthorization.scrubber_asn == filters["scrubber_asn"]
            )
        if filters.get("customer_asn") is not None:
            stmt = stmt.where(
                ScrubberAuthorization.customer_asn == filters["customer_asn"]
            )
        if filters.get("customer_prefix"):
            stmt = stmt.where(
                ScrubberAuthorization.customer_prefix == filters["customer_prefix"]
            )
        if filters.get("status"):
            stmt = stmt.where(ScrubberAuthorization.status == filters["status"])

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_scrubber_authorization(
    db: AsyncSession,
    authorization: ScrubberAuthorization,
    auth_update: ScrubberAuthorizationUpdate,
) -> ScrubberAuthorization:
    """更新清洗商授权。

    Args:
        db: 异步数据库会话
        authorization: 待更新的清洗商授权对象
        auth_update: 更新数据

    Returns:
        更新后的清洗商授权对象
    """
    update_data = auth_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(authorization, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(authorization)

    logger.info(
        "清洗商授权已更新",
        auth_id=authorization.id,
    )
    return authorization


async def delete_scrubber_authorization(
    db: AsyncSession, authorization: ScrubberAuthorization
) -> None:
    """删除清洗商授权。"""
    await db.delete(authorization)
    await db.commit()

    logger.info(
        "清洗商授权已删除",
        auth_id=authorization.id,
    )


async def check_scrubber_authorization(
    db: AsyncSession,
    scrubber_asn: int,
    prefix: str,
    at_time: datetime | None = None,
) -> ScrubberAuthorization | None:
    """检查清洗授权。

    检查指定清洗商 AS 是否有对指定前缀的有效授权。

    匹配条件：
    - 清洗商 AS 号匹配
    - 客户前缀匹配
    - 授权状态为 active
    - 指定时间在授权时间窗内（默认为当前时间）

    Args:
        db: 异步数据库会话
        scrubber_asn: 清洗商 AS 号
        prefix: 客户前缀
        at_time: 检查时间点（默认为当前时间）

    Returns:
        匹配的清洗商授权对象，无匹配返回 None
    """
    check_time = at_time or datetime.now(timezone.utc)

    stmt = (
        select(ScrubberAuthorization)
        .where(ScrubberAuthorization.scrubber_asn == scrubber_asn)
        .where(ScrubberAuthorization.customer_prefix == prefix)
        .where(ScrubberAuthorization.status == "active")
        .where(ScrubberAuthorization.authorized_at <= check_time)
        .where(ScrubberAuthorization.expires_at >= check_time)
        .order_by(ScrubberAuthorization.expires_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


__all__ = [
    "check_scrubber_authorization",
    "count_scrubber_authorizations",
    "create_scrubber_authorization",
    "delete_scrubber_authorization",
    "get_scrubber_authorization",
    "get_scrubber_authorizations",
    "update_scrubber_authorization",
]
