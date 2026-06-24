"""系统初始化数据：内置角色、权限、超级管理员账号。

在应用启动时调用 ``init_system_data()``，如果数据库为空则自动初始化。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rbac import ALL_PERMISSIONS, SYSTEM_ROLES
from app.core.security import get_password_hash
from app.core.database import async_session_factory
from app.models.user import Permission, Role, User

logger = get_logger("init_data")


async def _init_permissions(db: AsyncSession) -> dict[str, int]:
    """初始化系统权限，返回权限编码到 ID 的映射。

    如果权限已存在（如迁移脚本已插入），则直接加载映射。
    """
    # 加载现有权限
    result = await db.execute(select(Permission))
    existing_perms = {p.code: p for p in result.scalars().all()}

    if existing_perms:
        logger.info("权限数据已存在，跳过初始化", count=len(existing_perms))
        return {code: p.id for code, p in existing_perms.items()}

    perm_map: dict[str, int] = {}
    for perm_data in ALL_PERMISSIONS:
        perm = Permission(
            name=perm_data["name"],
            code=perm_data["code"],
            resource=perm_data["resource"],
            action=perm_data["action"],
            description=perm_data.get("description"),
        )
        db.add(perm)
    await db.flush()

    # 获取插入后的 ID
    result = await db.execute(select(Permission))
    for perm in result.scalars().all():
        perm_map[perm.code] = perm.id

    logger.info("系统权限初始化完成", count=len(perm_map))
    return perm_map


async def _init_roles(
    db: AsyncSession, perm_map: dict[str, int]
) -> dict[str, int]:
    """初始化系统角色并建立角色-权限关联，返回角色编码到 ID 的映射。

    如果角色已存在（如迁移脚本已插入），则仅补全权限关联。
    """
    # 加载现有角色
    result = await db.execute(select(Role))
    existing_roles = {r.code: r for r in result.scalars().all()}
    role_map: dict[str, int] = {code: r.id for code, r in existing_roles.items()}

    # 创建缺失的角色
    created = False
    for role_code, role_def in SYSTEM_ROLES.items():
        if role_code not in existing_roles:
            role = Role(
                name=str(role_def["name"]),
                code=role_code,
                description=str(role_def.get("description", "")),
                is_system=True,
            )
            db.add(role)
            existing_roles[role_code] = role
            created = True

    if created:
        await db.flush()
        # 重新加载以获取 ID
        for role_code, role in existing_roles.items():
            if role.id is None:
                result = await db.execute(
                    select(Role).where(Role.code == role_code)
                )
                db_role = result.scalar_one()
                existing_roles[role_code] = db_role
                role_map[role_code] = db_role.id

    # 始终确保角色-权限关联正确（即使角色已存在）
    for role_code, role_def in SYSTEM_ROLES.items():
        role = existing_roles.get(role_code)
        if role is None:
            continue
        perm_codes = role_def.get("permissions", [])
        if "*" in perm_codes:
            # 超级管理员拥有全部权限
            all_perms = await db.execute(select(Permission))
            role.permissions = list(all_perms.scalars().all())
        else:
            perm_ids = [perm_map[c] for c in perm_codes if c in perm_map]
            if perm_ids:
                perms_result = await db.execute(
                    select(Permission).where(Permission.id.in_(perm_ids))
                )
                role.permissions = list(perms_result.scalars().all())
            else:
                role.permissions = []

    await db.flush()
    logger.info("系统角色初始化完成", count=len(role_map))
    return role_map


async def _init_super_admin(db: AsyncSession) -> None:
    """初始化默认超级管理员账号。"""
    # 检查是否已有超级管理员
    result = await db.execute(
        select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)
    )
    if result.scalar_one_or_none() is not None:
        logger.info("超级管理员账号已存在，跳过创建")
        return

    # 获取 super_admin 角色
    result = await db.execute(
        select(Role).where(Role.code == "super_admin")
    )
    super_admin_role = result.scalar_one_or_none()

    admin = User(
        email=settings.DEFAULT_ADMIN_EMAIL,
        username=settings.DEFAULT_ADMIN_USERNAME,
        full_name="系统管理员",
        hashed_password=get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
        is_active=True,
        is_superuser=True,
        status="active",
        must_change_password=True,  # 首次登录强制修改密码
    )
    if super_admin_role is not None:
        admin.roles = [super_admin_role]

    db.add(admin)
    await db.flush()

    logger.info(
        "默认超级管理员已创建",
        username=settings.DEFAULT_ADMIN_USERNAME,
        email=settings.DEFAULT_ADMIN_EMAIL,
    )


async def init_system_data() -> None:
    """初始化系统数据：权限、角色、超级管理员。

    在应用启动时调用，如果数据已存在则跳过。
    """
    logger.info("开始系统数据初始化检查...")

    async with async_session_factory() as db:
        try:
            perm_map = await _init_permissions(db)
            await _init_roles(db, perm_map)
            await _init_super_admin(db)
            await db.commit()
            logger.info("系统数据初始化完成")
        except Exception as e:
            await db.rollback()
            logger.error("系统数据初始化失败", error=str(e))
            raise
