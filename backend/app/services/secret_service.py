"""敏感数据加密存储与密钥托管服务。

提供敏感数据（如集成配置的 ``auth_config``）的加解密接口，以及
密钥轮换时对数据库中已加密数据的批量重加密能力。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.encryption import (
    decrypt_data,
    decrypt_dict,
    encrypt_data,
    encrypt_dict,
    rotate_encryption_key,
)
from app.core.logging import get_logger
from app.models.integration import IntegrationConfig

logger = get_logger("app.services.secret_service")

# IntegrationConfig.auth_config 中需要加密的敏感字段名
SENSITIVE_AUTH_FIELDS: list[str] = [
    "password",
    "token",
    "api_key",
    "secret",
    "secret_key",
    "access_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
    "passphrase",
]


def encrypt_secret(value: str) -> str:
    """加密敏感数据。

    Args:
        value: 待加密的明文字符串

    Returns:
        Fernet 加密后的密文字符串
    """
    return encrypt_data(value)


def decrypt_secret(encrypted: str) -> str:
    """解密敏感数据。

    Args:
        encrypted: Fernet 加密后的密文字符串

    Returns:
        解密后的明文字符串

    Raises:
        cryptography.fernet.InvalidToken: 密钥不匹配或密文损坏。
    """
    return decrypt_data(encrypted)


def encrypt_auth_config(auth_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """加密 IntegrationConfig.auth_config 中的敏感字段。

    Args:
        auth_config: 原始认证配置字典

    Returns:
        敏感字段已加密的新字典；输入为 None 时返回 None
    """
    if auth_config is None:
        return None
    return encrypt_dict(auth_config, SENSITIVE_AUTH_FIELDS)


def decrypt_auth_config(
    auth_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """解密 IntegrationConfig.auth_config 中的敏感字段。

    Args:
        auth_config: 包含加密字段的认证配置字典

    Returns:
        敏感字段已解密的新字典；输入为 None 时返回 None
    """
    if auth_config is None:
        return None
    return decrypt_dict(auth_config, SENSITIVE_AUTH_FIELDS)


async def rotate_secrets(old_key: str, new_key: str) -> int:
    """批量轮换数据库中的加密数据。

    遍历所有 IntegrationConfig 记录，使用旧密钥解密 ``auth_config``
    中的敏感字段，再用新密钥重新加密并写回数据库。

    Args:
        old_key: 旧加密密钥（base64-url 编码的 Fernet 密钥）
        new_key: 新加密密钥（base64-url 编码的 Fernet 密钥）

    Returns:
        成功轮换的记录数
    """
    from cryptography.fernet import Fernet, InvalidToken

    from app.core.database import async_session_factory

    old_fernet = Fernet(old_key.encode("utf-8") if isinstance(old_key, str) else old_key)
    new_fernet = Fernet(new_key.encode("utf-8") if isinstance(new_key, str) else new_key)

    rotated_count = 0

    # 使用独立的数据库会话执行批量轮换，避免依赖调用方会话
    async with async_session_factory() as db:
        stmt = select(IntegrationConfig).where(IntegrationConfig.auth_config.isnot(None))
        result = await db.execute(stmt)
        integrations = result.scalars().all()

        for integration in integrations:
            auth_config = integration.auth_config
            if not auth_config:
                continue

            new_auth_config: dict[str, Any] = dict(auth_config)
            changed = False

            for field in SENSITIVE_AUTH_FIELDS:
                if field not in new_auth_config:
                    continue
                value = new_auth_config[field]
                if not isinstance(value, str) or not value:
                    continue
                try:
                    plaintext = old_fernet.decrypt(value.encode("utf-8")).decode("utf-8")
                except InvalidToken:
                    # 该字段可能未加密或已用其他密钥加密，跳过
                    logger.warning(
                        "轮换时字段解密失败，跳过",
                        integration_id=integration.id,
                        field=field,
                    )
                    continue
                new_auth_config[field] = new_fernet.encrypt(plaintext.encode("utf-8")).decode(
                    "utf-8"
                )
                changed = True

            if changed:
                integration.auth_config = new_auth_config
                rotated_count += 1

        await db.commit()

    # 触发密钥轮换后续处理（清理缓存等）
    rotate_encryption_key(old_key, new_key)

    logger.info(
        "加密数据批量轮换完成",
        rotated_count=rotated_count,
    )
    return rotated_count


__all__ = [
    "SENSITIVE_AUTH_FIELDS",
    "decrypt_auth_config",
    "decrypt_secret",
    "encrypt_auth_config",
    "encrypt_secret",
    "rotate_secrets",
]
