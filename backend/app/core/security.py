"""安全工具：密码哈希、JWT 令牌管理、敏感数据加密与密钥轮换。"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.core.security")

# 密码哈希上下文（bcrypt）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希密码是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码的 bcrypt 哈希值。"""
    return pwd_context.hash(password)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """创建 JWT 访问令牌。

    Args:
        subject: 令牌主体（通常为用户 ID）
        expires_delta: 自定义过期时间，未提供则使用默认配置
        extra_claims: 额外的声明信息

    Returns:
        编码后的 JWT 字符串
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解码并验证 JWT 令牌。

    Args:
        token: JWT 字符串

    Returns:
        解码后的载荷字典，验证失败返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


# ──────────────────────────────────────────────
# 敏感数据加密（Fernet 对称加密）
# ──────────────────────────────────────────────


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


def encrypt_sensitive_data(data: str) -> str:
    """加密敏感数据。

    使用 Fernet 对称加密算法加密字符串，返回可逆的密文字符串。

    Args:
        data: 待加密的明文字符串

    Returns:
        Fernet 加密后的密文字符串
    """
    from cryptography.fernet import Fernet

    fernet = Fernet(get_encryption_key())
    return fernet.encrypt(data.encode("utf-8")).decode("utf-8")


def decrypt_sensitive_data(encrypted: str) -> str:
    """解密敏感数据。

    使用 Fernet 对称加密算法解密 ``encrypt_sensitive_data`` 生成的密文。

    Args:
        encrypted: Fernet 加密后的密文字符串

    Returns:
        解密后的明文字符串

    Raises:
        cryptography.fernet.InvalidToken: 密钥不匹配或密文损坏。
    """
    from cryptography.fernet import Fernet, InvalidToken

    fernet = Fernet(get_encryption_key())
    try:
        return fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("敏感数据解密失败：密钥不匹配或密文损坏")
        raise


# ──────────────────────────────────────────────
# 字段级加密（用于数据库敏感字段自动加解密）
# ──────────────────────────────────────────────


@lru_cache
def get_field_encryption_key() -> bytes:
    """获取字段级加密专用密钥。

    优先级：
    1. ``settings.FIELD_ENCRYPTION_KEY``（推荐生产环境显式配置）
    2. ``settings.ENCRYPTION_KEY``
    3. 基于 ``settings.SECRET_KEY`` 派生的 32 字节 base64-url 编码密钥

    Returns:
        Fernet 兼容的 32 字节 base64-url 编码密钥。
    """
    if settings.FIELD_ENCRYPTION_KEY:
        return settings.FIELD_ENCRYPTION_KEY.encode("utf-8")
    if settings.ENCRYPTION_KEY:
        return settings.ENCRYPTION_KEY.encode("utf-8")
    # 基于 SECRET_KEY 派生固定 32 字节密钥
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_field(value: Any) -> str | None:
    """加密字段值（字段级加密）。

    将任意可 JSON 序列化的值加密为字符串，便于存储到数据库文本字段。
    使用独立的字段级加密密钥（``FIELD_ENCRYPTION_KEY``），与通用加密密钥
    隔离，便于单独轮换。

    Args:
        value: 待加密的字段值（字符串、字典、列表等可 JSON 序列化对象）

    Returns:
        Fernet 加密后的密文字符串；输入为 None 时返回 None

    Raises:
        cryptography.fernet.InvalidToken: 加密失败。
    """
    if value is None:
        return None
    from cryptography.fernet import Fernet

    # 非字符串值先 JSON 序列化，保留类型信息
    if isinstance(value, str):
        plaintext = value
    else:
        plaintext = json.dumps(value, ensure_ascii=False, default=str)

    fernet = Fernet(get_field_encryption_key())
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(encrypted: str | None) -> Any:
    """解密字段值（字段级加密）。

    解密 :func:`encrypt_field` 生成的密文，自动尝试还原原始类型
    （字符串、字典、列表等）。解密失败时返回原始值并记录警告日志，
    避免影响业务流程。

    Args:
        encrypted: Fernet 加密后的密文字符串

    Returns:
        解密后的原始值；输入为 None 时返回 None；
        解密失败时返回原始输入值。
    """
    if encrypted is None:
        return None
    if not isinstance(encrypted, str) or not encrypted:
        return encrypted

    from cryptography.fernet import Fernet, InvalidToken

    fernet = Fernet(get_field_encryption_key())
    try:
        plaintext = fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("字段解密失败：密钥不匹配或密文损坏，返回原始值")
        return encrypted

    # 尝试还原 JSON 类型（字典、列表等）
    try:
        return json.loads(plaintext)
    except (json.JSONDecodeError, TypeError):
        # 非 JSON 字符串直接返回
        return plaintext


# ──────────────────────────────────────────────
# 密钥轮换
# ──────────────────────────────────────────────


def rotate_secret_key() -> str:
    """生成新的 JWT 密钥并将当前密钥归档到旧密钥列表。

    本函数仅生成新密钥并返回，调用方需自行将旧密钥写入
    ``settings.PREVIOUS_SECRET_KEYS`` 与持久化配置中，以保证
    令牌验证的平滑过渡。

    Returns:
        新生成的随机密钥字符串（64 个十六进制字符）。
    """
    new_key = secrets.token_hex(32)
    logger.info(
        "JWT 密钥已轮换",
        rotation_interval_days=settings.SECRET_KEY_ROTATION_INTERVAL_DAYS,
    )
    return new_key


def verify_token_with_rotation(token: str) -> dict[str, Any] | None:
    """使用当前密钥或旧密钥验证 JWT 令牌。

    在密钥轮换过渡期内，旧令牌仍可使用旧密钥验证。本函数依次尝试
    当前密钥与 ``settings.PREVIOUS_SECRET_KEYS`` 中的旧密钥进行验证。

    Args:
        token: JWT 令牌字符串

    Returns:
        解码后的载荷字典，全部密钥验证失败返回 None
    """
    # 先用当前密钥验证
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        pass

    # 依次尝试旧密钥
    for old_key in settings.PREVIOUS_SECRET_KEYS:
        try:
            return jwt.decode(token, old_key, algorithms=[settings.ALGORITHM])
        except JWTError:
            continue

    return None


__all__ = [
    "create_access_token",
    "decode_access_token",
    "decrypt_field",
    "decrypt_sensitive_data",
    "encrypt_field",
    "encrypt_sensitive_data",
    "get_encryption_key",
    "get_field_encryption_key",
    "get_password_hash",
    "rotate_secret_key",
    "verify_password",
    "verify_token_with_rotation",
]
