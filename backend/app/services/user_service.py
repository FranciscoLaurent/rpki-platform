"""用户服务：用户 CRUD 与角色分配。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash
from app.models.user import Role, User
from app.schemas.auth import UserUpdate


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    """根据 ID 获取用户（预加载角色与权限）。"""
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """根据用户名获取用户。"""
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.username == username)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_users(db: AsyncSession, skip: int = 0, limit: int = 20) -> list[User]:
    """获取用户列表（预加载角色）。"""
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .offset(skip)
        .limit(limit)
        .order_by(User.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_users(db: AsyncSession) -> int:
    """统计用户总数。"""
    from sqlalchemy import func

    stmt = select(func.count(User.id))
    result = await db.execute(stmt)
    return result.scalar_one()


async def update_user(db: AsyncSession, user: User, user_update: UserUpdate) -> User:
    """更新用户信息。

    Args:
        db: 异步数据库会话
        user: 待更新的用户对象
        user_update: 更新数据

    Returns:
        更新后的用户对象
    """
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.password is not None:
        user.hashed_password = get_password_hash(user_update.password)
    if user_update.is_active is not None:
        user.is_active = user_update.is_active

    await db.flush()
    await db.commit()
    await db.refresh(user)
    return user


async def assign_roles(db: AsyncSession, user_id: int, role_ids: list[int]) -> User | None:
    """为用户分配角色（替换原有角色）。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        role_ids: 角色 ID 列表

    Returns:
        更新后的用户对象，用户不存在则返回 None。
    """
    user = await get_user(db, user_id)
    if user is None:
        return None

    # 查询指定角色
    if role_ids:
        stmt = select(Role).where(Role.id.in_(role_ids))
        result = await db.execute(stmt)
        roles = list(result.scalars().all())
        user.roles = roles
    else:
        user.roles = []

    await db.flush()
    await db.commit()
    await db.refresh(user)
    return user


async def get_all_roles(db: AsyncSession) -> list[Role]:
    """获取所有角色列表（预加载权限）。"""
    stmt = select(Role).options(selectinload(Role.permissions))
    result = await db.execute(stmt)
    return list(result.scalars().all())
