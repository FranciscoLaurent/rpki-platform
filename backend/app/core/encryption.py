"""敏感数据加密与密钥轮换工具。

基于 Fernet 对称加密（AES-128-CBC + HMAC-SHA256）提供字符串与字典
级别的加解密能力，并支持密钥轮换。

加密密钥来源优先级：
1. ``settings.ENCRYPTION_KEY``（推荐生产环境显式配置）
2. 基于 ``settings.SECRET_KEY`` 派生的 32 字节 base64-url 编码密钥
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.core.encryption")


@lru_cache
def get_encryption_key() -> bytes:
    """获取 Fernet 加密密钥。

    优先使用 ``settings.ENCRYPTION_KEY``；若未配置，则基于
    ``settings.SECRET_KEY`` 派生 32 字节密钥并 base64-url 编码，
    以满足 Fernet 密钥格式要求。

    Returns:
        Fernet 兼容的 32 字节 base64-url 编码密钥。
    """
    if settings.ENCRYPTION_KEY:
        return settings.ENCRYPTION_KEY.encode("utf-8")

    # 基于 SECRET_KEY 派生固定 32 字节密钥
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet(key: bytes | None = None):
    """构造 Fernet 实例，未指定 key 时使用当前加密密钥。"""
    from cryptography.fernet import Fernet

    return Fernet(key if key is not None else get_encryption_key())


def encrypt_data(plaintext: str) -> str:
    """加密敏感数据。

    使用 Fernet 对称加密算法加密字符串，返回可逆的密文字符串。

    Args:
        plaintext: 待加密的明文字符串

    Returns:
        Fernet 加密后的密文字符串
    """
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_data(ciphertext: str) -> str:
    """解密敏感数据。

    使用 Fernet 对称加密算法解密 :func:`encrypt_data` 生成的密文。

    Args:
        ciphertext: Fernet 加密后的密文字符串

    Returns:
        解密后的明文字符串

    Raises:
        cryptography.fernet.InvalidToken: 密钥不匹配或密文损坏。
    """
    from cryptography.fernet import InvalidToken

    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("敏感数据解密失败：密钥不匹配或密文损坏")
        raise


def rotate_encryption_key(old_key: str, new_key: str) -> None:
    """加密密钥轮换接口。

    本函数为密钥轮换的协调入口，实际的数据重加密应由
    :func:`app.services.secret_service.rotate_secrets` 在数据库层面
    批量执行。此处仅记录审计日志并清理密钥缓存，使后续加解密使用新密钥。

    Args:
        old_key: 旧加密密钥（base64-url 编码的 Fernet 密钥）
        new_key: 新加密密钥（base64-url 编码的 Fernet 密钥）
    """
    logger.info(
        "加密密钥轮换已触发",
        rotation_interval_days=settings.KEY_ROTATION_INTERVAL_DAYS,
    )
    # 清除密钥缓存，使后续调用重新读取 settings.ENCRYPTION_KEY
    get_encryption_key.cache_clear()
    logger.info("加密密钥缓存已清理，后续加解密将使用新密钥")


# ──────────────────────────────────────────────
# 字典级加解密
# ──────────────────────────────────────────────


def encrypt_dict(
    data: dict[str, Any],
    sensitive_fields: list[str],
) -> dict[str, Any]:
    """加密字典中的敏感字段。

    对字典中指定的敏感字段进行加密，返回新的字典（原字典不被修改）。
    非敏感字段保持原样。若敏感字段的值不是字符串，则先 JSON 序列化。

    Args:
        data: 原始字典
        sensitive_fields: 需要加密的字段名列表

    Returns:
        新字典，敏感字段已被加密
    """
    import json

    result = dict(data)
    for field in sensitive_fields:
        if field not in result:
            continue
        value = result[field]
        if value is None:
            continue
        if isinstance(value, str):
            plaintext = value
        else:
            plaintext = json.dumps(value, ensure_ascii=False)
        result[field] = encrypt_data(plaintext)
    return result


def decrypt_dict(
    data: dict[str, Any],
    sensitive_fields: list[str],
) -> dict[str, Any]:
    """解密字典中的敏感字段。

    对字典中指定的敏感字段进行解密，返回新的字典（原字典不被修改）。
    解密失败的字段保留原值并记录警告日志。

    Args:
        data: 包含加密字段的字典
        sensitive_fields: 需要解密的字段名列表

    Returns:
        新字典，敏感字段已被解密
    """
    from cryptography.fernet import InvalidToken

    result = dict(data)
    for field in sensitive_fields:
        if field not in result:
            continue
        value = result[field]
        if not isinstance(value, str) or not value:
            continue
        fernet = _get_fernet()
        try:
            result[field] = fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.warning(
                "字典字段解密失败，保留原值",
                field=field,
            )
    return result


__all__ = [
    "decrypt_data",
    "decrypt_dict",
    "encrypt_data",
    "encrypt_dict",
    "get_encryption_key",
    "rotate_encryption_key",
]
