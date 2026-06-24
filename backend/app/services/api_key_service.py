"""API Key 服务：创建、验证、查询、更新与删除 API 密钥。

密钥采用 ``rpk_<prefix>.<random>`` 格式，存储时仅保留 bcrypt 哈希，
明文密钥仅在创建时返回一次。验证时通过前缀快速定位候选记录，
再使用 bcrypt 比对哈希。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import get_password_hash, verify_password
from app.models.api_key import ApiKey

logger = get_logger("app.api_key_service")

# API Key 前缀，用于识别本系统签发的密钥
_API_KEY_PREFIX = "rpk"
# 密钥前缀展示长度（用于列表展示与识别）
_KEY_PREFIX_DISPLAY_LEN = 12


def _generate_api_key() -> tuple[str, str]:
    """生成新的 API Key 明文与展示前缀。

    格式：``rpk_<8位前缀>.<32位随机字符>``

    Returns:
        (plaintext_key, key_prefix) 元组。
        - plaintext_key: 完整明文密钥（仅返回一次）
        - key_prefix: 用于展示与识别的前缀（如 ``rpk_a1b2c3d4``）
    """
    prefix_part = secrets.token_hex(4)  # 8 个十六进制字符
    secret_part = secrets.token_hex(16)  # 32 个十六进制字符
    plaintext = f"{_API_KEY_PREFIX}_{prefix_part}.{secret_part}"
    display_prefix = f"{_API_KEY_PREFIX}_{prefix_part}"
    return plaintext, display_prefix


async def create_api_key(
    db: AsyncSession,
    user_id: int,
    name: str,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
    tenant_id: int | None = None,
) -> tuple[ApiKey, str]:
    """创建 API Key。

    生成新的密钥明文与哈希，明文仅在此处返回一次。

    Args:
        db: 异步数据库会话
        user_id: 所属用户 ID
        name: 密钥名称
        scopes: 权限范围列表
        expires_at: 过期时间，为空表示永不过期
        tenant_id: 租户 ID

    Returns:
        (ApiKey 对象, 明文密钥) 元组。明文密钥需由调用方立即返回给客户端。
    """
    plaintext, key_prefix = _generate_api_key()
    key_hash = get_password_hash(plaintext)

    api_key = ApiKey(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=user_id,
        tenant_id=tenant_id,
        scopes=scopes or [],
        is_active=True,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    await db.commit()
    await db.refresh(api_key)

    logger.info(
        "API Key 创建成功",
        api_key_id=api_key.id,
        name=name,
        user_id=user_id,
    )
    return api_key, plaintext


async def verify_api_key(db: AsyncSession, key: str) -> ApiKey | None:
    """验证 API Key 并返回对应的 ApiKey 对象。

    验证流程：
    1. 解析密钥前缀，按前缀查询候选记录
    2. 使用 bcrypt 比对哈希
    3. 检查启用状态与过期时间
    4. 更新最后使用时间

    Args:
        db: 异步数据库会话
        key: 明文 API Key

    Returns:
        验证成功返回 ApiKey 对象，失败返回 None
    """
    if not key or not key.startswith(f"{_API_KEY_PREFIX}_"):
        return None

    # 解析前缀部分（rpk_xxxxxxxx）
    parts = key.split(".", 1)
    if len(parts) != 2:
        return None
    key_prefix = parts[0]

    # 按前缀查询候选记录
    stmt = select(ApiKey).where(
        ApiKey.key_prefix == key_prefix,
        ApiKey.is_active.is_(True),
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        return None

    # 检查过期时间
    if api_key.expires_at is not None:
        now = datetime.now(timezone.utc)
        if api_key.expires_at <= now:
            logger.warning(
                "API Key 已过期",
                api_key_id=api_key.id,
                key_prefix=key_prefix,
            )
            return None

    # 比对哈希
    if not verify_password(key, api_key.key_hash):
        logger.warning(
            "API Key 哈希比对失败",
            api_key_id=api_key.id,
            key_prefix=key_prefix,
        )
        return None

    # 更新最后使用时间
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()

    return api_key


async def list_api_keys(
    db: AsyncSession,
    user_id: int | None = None,
    tenant_id: int | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ApiKey]:
    """查询 API Key 列表。

    Args:
        db: 异步数据库会话
        user_id: 按用户 ID 过滤
        tenant_id: 按租户 ID 过滤
        is_active: 按启用状态过滤
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        API Key 列表
    """
    stmt = select(ApiKey)
    if user_id is not None:
        stmt = stmt.where(ApiKey.user_id == user_id)
    if tenant_id is not None:
        stmt = stmt.where(ApiKey.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(ApiKey.is_active.is_(is_active))

    stmt = stmt.order_by(ApiKey.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_api_keys(
    db: AsyncSession,
    user_id: int | None = None,
    tenant_id: int | None = None,
    is_active: bool | None = None,
) -> int:
    """统计 API Key 数量。"""
    from sqlalchemy import func

    stmt = select(func.count(ApiKey.id))
    if user_id is not None:
        stmt = stmt.where(ApiKey.user_id == user_id)
    if tenant_id is not None:
        stmt = stmt.where(ApiKey.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(ApiKey.is_active.is_(is_active))

    result = await db.execute(stmt)
    return result.scalar_one()


async def get_api_key(db: AsyncSession, api_key_id: int) -> ApiKey | None:
    """根据 ID 获取 API Key。"""
    stmt = select(ApiKey).where(ApiKey.id == api_key_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_api_key(db: AsyncSession, api_key_id: int) -> bool:
    """删除 API Key。

    Args:
        db: 异步数据库会话
        api_key_id: API Key ID

    Returns:
        是否删除成功（不存在则返回 False）
    """
    api_key = await get_api_key(db, api_key_id)
    if api_key is None:
        return False
    await db.delete(api_key)
    await db.commit()
    logger.info("API Key 已删除", api_key_id=api_key_id)
    return True


async def update_api_key(
    db: AsyncSession,
    api_key: ApiKey,
    name: str | None = None,
    scopes: list[str] | None = None,
    is_active: bool | None = None,
    expires_at: datetime | None = None,
) -> ApiKey:
    """更新 API Key 属性。

    Args:
        db: 异步数据库会话
        api_key: 待更新的 ApiKey 对象
        name: 新名称
        scopes: 新权限范围
        is_active: 新启用状态
        expires_at: 新过期时间

    Returns:
        更新后的 ApiKey 对象
    """
    if name is not None:
        api_key.name = name
    if scopes is not None:
        api_key.scopes = scopes
    if is_active is not None:
        api_key.is_active = is_active
    if expires_at is not None:
        api_key.expires_at = expires_at

    await db.flush()
    await db.commit()
    await db.refresh(api_key)
    return api_key


__all__ = [
    "count_api_keys",
    "create_api_key",
    "delete_api_key",
    "get_api_key",
    "list_api_keys",
    "update_api_key",
    "verify_api_key",
]
