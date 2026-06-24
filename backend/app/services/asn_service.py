"""ASN 服务：CRUD 与按 ASN 号查询。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asn import ASN
from app.schemas.asn import ASNCreate, ASNUpdate


async def create_asn(db: AsyncSession, asn_create: ASNCreate) -> ASN:
    """创建 ASN。

    Args:
        db: 异步数据库会话
        asn_create: ASN 创建数据

    Returns:
        创建后的 ASN 对象

    Raises:
        ValueError: ASN 号已存在
    """
    existing = await get_asn_by_number(db, asn_create.asn)
    if existing is not None:
        raise ValueError(f"ASN {asn_create.asn} 已存在")

    asn = ASN(
        asn=asn_create.asn,
        name=asn_create.name,
        asn_type=asn_create.asn_type,
        status=asn_create.status,
        risk_profile=asn_create.risk_profile,
        contact_name=asn_create.contact_name,
        contact_email=asn_create.contact_email,
        noc_phone=asn_create.noc_phone,
        emergency_contact=asn_create.emergency_contact,
        relationship_tags=asn_create.relationship_tags,
        description=asn_create.description,
    )
    db.add(asn)
    await db.flush()
    await db.commit()
    await db.refresh(asn)
    return asn


async def get_asn(db: AsyncSession, asn_id: int) -> ASN | None:
    """根据 ID 获取 ASN。"""
    stmt = select(ASN).where(ASN.id == asn_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_asn_by_number(db: AsyncSession, asn: int) -> ASN | None:
    """按 ASN 号查询。"""
    stmt = select(ASN).where(ASN.asn == asn)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_asns(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ASN]:
    """分页查询 ASN，支持按 asn_type/status 过滤。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``asn_type``、``status``、``asn``、``name``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        ASN 列表
    """
    stmt = select(ASN)
    if filters:
        if filters.get("asn_type"):
            stmt = stmt.where(ASN.asn_type == filters["asn_type"])
        if filters.get("status"):
            stmt = stmt.where(ASN.status == filters["status"])
        if filters.get("asn") is not None:
            stmt = stmt.where(ASN.asn == filters["asn"])
        if filters.get("name"):
            stmt = stmt.where(ASN.name.ilike(f"%{filters['name']}%"))

    stmt = stmt.order_by(ASN.asn).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_asns(db: AsyncSession, filters: dict[str, Any] | None = None) -> int:
    """统计 ASN 数量。"""
    stmt = select(func.count(ASN.id))
    if filters:
        if filters.get("asn_type"):
            stmt = stmt.where(ASN.asn_type == filters["asn_type"])
        if filters.get("status"):
            stmt = stmt.where(ASN.status == filters["status"])
        if filters.get("asn") is not None:
            stmt = stmt.where(ASN.asn == filters["asn"])
        if filters.get("name"):
            stmt = stmt.where(ASN.name.ilike(f"%{filters['name']}%"))

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_asn(db: AsyncSession, asn: ASN, asn_update: ASNUpdate) -> ASN:
    """更新 ASN。

    Args:
        db: 异步数据库会话
        asn: 待更新的 ASN 对象
        asn_update: 更新数据

    Returns:
        更新后的 ASN 对象
    """
    update_data = asn_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asn, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(asn)
    return asn


async def delete_asn(db: AsyncSession, asn: ASN) -> None:
    """删除 ASN。"""
    await db.delete(asn)
    await db.commit()


__all__ = [
    "count_asns",
    "create_asn",
    "delete_asn",
    "get_asn",
    "get_asn_by_number",
    "get_asns",
    "update_asn",
]
