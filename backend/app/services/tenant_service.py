"""租户服务：租户 CRUD、成员管理与配置管理。

提供租户生命周期管理、成员关系维护以及租户级配置的读写能力。
所有操作均通过异步 SQLAlchemy 会话进行。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tenant import Tenant, TenantMember
from app.schemas.tenant import (
    TenantCreate,
    TenantMemberCreate,
    TenantMemberUpdate,
    TenantSettingsUpdate,
    TenantUpdate,
)

logger = get_logger("app.tenant_service")


# ──────────────────────────────────────────────
# 租户 CRUD
# ──────────────────────────────────────────────


async def create_tenant(db: AsyncSession, tenant_create: TenantCreate) -> Tenant:
    """创建租户。

    Args:
        db: 异步数据库会话
        tenant_create: 租户创建数据

    Returns:
        创建后的 Tenant 对象

    Raises:
        ValueError: slug 已存在
    """
    existing = await get_tenant_by_slug(db, tenant_create.slug)
    if existing is not None:
        raise ValueError(f"租户 slug '{tenant_create.slug}' 已存在")

    tenant = Tenant(
        name=tenant_create.name,
        slug=tenant_create.slug,
        status="active",
        settings=tenant_create.settings,
        max_users=tenant_create.max_users,
    )
    db.add(tenant)
    await db.flush()
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "租户创建成功",
        tenant_id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
    )
    return tenant


async def get_tenant(db: AsyncSession, tenant_id: int) -> Tenant | None:
    """根据 ID 获取租户。"""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    """根据 slug 获取租户。"""
    stmt = select(Tenant).where(Tenant.slug == slug)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_tenants(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Tenant]:
    """分页查询租户列表。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``status``、``name``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        租户列表
    """
    stmt = select(Tenant)
    if filters:
        if filters.get("status"):
            stmt = stmt.where(Tenant.status == filters["status"])
        if filters.get("name"):
            stmt = stmt.where(Tenant.name.ilike(f"%{filters['name']}%"))

    stmt = stmt.order_by(Tenant.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_tenants(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计租户数量。"""
    stmt = select(func.count(Tenant.id))
    if filters:
        if filters.get("status"):
            stmt = stmt.where(Tenant.status == filters["status"])
        if filters.get("name"):
            stmt = stmt.where(Tenant.name.ilike(f"%{filters['name']}%"))

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_tenant(
    db: AsyncSession, tenant: Tenant, tenant_update: TenantUpdate
) -> Tenant:
    """更新租户信息。

    Args:
        db: 异步数据库会话
        tenant: 待更新的 Tenant 对象
        tenant_update: 更新数据

    Returns:
        更新后的 Tenant 对象
    """
    update_data = tenant_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(tenant)

    logger.info("租户更新成功", tenant_id=tenant.id)
    return tenant


async def delete_tenant(db: AsyncSession, tenant: Tenant) -> None:
    """删除租户。

    同时级联删除该租户的成员关系（由 ORM 外键级联约束保证）。

    Args:
        db: 异步数据库会话
        tenant: 待删除的 Tenant 对象
    """
    tenant_id = tenant.id
    await db.delete(tenant)
    await db.commit()
    logger.info("租户已删除", tenant_id=tenant_id)


# ──────────────────────────────────────────────
# 租户配置管理
# ──────────────────────────────────────────────


async def update_tenant_settings(
    db: AsyncSession,
    tenant: Tenant,
    settings_update: TenantSettingsUpdate,
) -> Tenant:
    """更新租户配置。

    整体替换租户的 ``settings`` 字段。

    Args:
        db: 异步数据库会话
        tenant: 待更新的 Tenant 对象
        settings_update: 配置更新数据

    Returns:
        更新后的 Tenant 对象
    """
    tenant.settings = settings_update.settings
    await db.flush()
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "租户配置更新成功",
        tenant_id=tenant.id,
    )
    return tenant


async def get_tenant_settings(db: AsyncSession, tenant: Tenant) -> dict[str, Any]:
    """获取租户配置。"""
    return dict(tenant.settings or {})


# ──────────────────────────────────────────────
# 租户成员管理
# ──────────────────────────────────────────────


async def add_member(
    db: AsyncSession,
    tenant_id: int,
    member_create: TenantMemberCreate,
) -> TenantMember:
    """添加租户成员。

    Args:
        db: 异步数据库会话
        tenant_id: 租户 ID
        member_create: 成员创建数据

    Returns:
        创建的 TenantMember 对象

    Raises:
        ValueError: 租户不存在、成员已存在或超出最大用户数限制
    """
    tenant = await get_tenant(db, tenant_id)
    if tenant is None:
        raise ValueError(f"租户 ID {tenant_id} 不存在")

    # 检查是否已是成员
    existing = await get_member(db, tenant_id, member_create.user_id)
    if existing is not None:
        raise ValueError(
            f"用户 {member_create.user_id} 已是租户 {tenant_id} 的成员"
        )

    # 检查最大用户数限制
    current_count = await count_members(db, tenant_id)
    if current_count >= tenant.max_users:
        raise ValueError(
            f"租户 {tenant_id} 已达最大用户数限制 {tenant.max_users}"
        )

    member = TenantMember(
        user_id=member_create.user_id,
        tenant_id=tenant_id,
        role=member_create.role,
    )
    db.add(member)
    await db.flush()
    await db.commit()
    await db.refresh(member)

    logger.info(
        "租户成员添加成功",
        tenant_id=tenant_id,
        user_id=member_create.user_id,
        role=member_create.role,
    )
    return member


async def get_member(
    db: AsyncSession, tenant_id: int, user_id: int
) -> TenantMember | None:
    """获取租户成员关系。"""
    stmt = select(TenantMember).where(
        TenantMember.tenant_id == tenant_id,
        TenantMember.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_member_by_id(
    db: AsyncSession, member_id: int
) -> TenantMember | None:
    """根据成员记录 ID 获取成员关系。"""
    stmt = select(TenantMember).where(TenantMember.id == member_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_members(
    db: AsyncSession, tenant_id: int
) -> list[TenantMember]:
    """获取租户全部成员列表。"""
    stmt = select(TenantMember).where(
        TenantMember.tenant_id == tenant_id
    ).order_by(TenantMember.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_members(db: AsyncSession, tenant_id: int) -> int:
    """统计租户成员数量。"""
    stmt = select(func.count(TenantMember.id)).where(
        TenantMember.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def update_member(
    db: AsyncSession,
    member: TenantMember,
    member_update: TenantMemberUpdate,
) -> TenantMember:
    """更新租户成员角色。"""
    member.role = member_update.role
    await db.flush()
    await db.commit()
    await db.refresh(member)

    logger.info(
        "租户成员角色更新",
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
    )
    return member


async def remove_member(db: AsyncSession, member: TenantMember) -> None:
    """移除租户成员。"""
    tenant_id = member.tenant_id
    user_id = member.user_id
    await db.delete(member)
    await db.commit()

    logger.info(
        "租户成员已移除",
        tenant_id=tenant_id,
        user_id=user_id,
    )


__all__ = [
    "add_member",
    "count_members",
    "count_tenants",
    "create_tenant",
    "delete_tenant",
    "get_member",
    "get_member_by_id",
    "get_tenant",
    "get_tenant_by_slug",
    "get_tenant_settings",
    "get_tenants",
    "list_members",
    "remove_member",
    "update_member",
    "update_tenant",
    "update_tenant_settings",
]
