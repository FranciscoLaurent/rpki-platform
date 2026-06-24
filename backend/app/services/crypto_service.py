"""敏感数据加密服务。

提供针对集成配置中凭据字段的加密/解密能力，用于保护数据库中
存储的敏感信息（如 API Key、密码、Token 等）。

底层使用 ``app.core.security`` 中的 Fernet 加密实现。
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.core.security import decrypt_sensitive_data, encrypt_sensitive_data

logger = get_logger("app.services.crypto_service")

# 标记字段已加密的前缀，避免重复加密
_ENCRYPTED_PREFIX = "enc::"


def encrypt_field(value: str | None) -> str | None:
    """加密单个敏感字段。

    若值为 ``None`` 或空字符串则原样返回；若值已被加密（带前缀）则跳过。

    Args:
        value: 待加密的明文字符串

    Returns:
        加密后的字符串（带 ``enc::`` 前缀），或原值
    """
    if value is None or value == "":
        return value
    if isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
        # 已加密，避免重复加密
        return value
    encrypted = encrypt_sensitive_data(value)
    return f"{_ENCRYPTED_PREFIX}{encrypted}"


def decrypt_field(value: str | None) -> str | None:
    """解密单个敏感字段。

    若值不带 ``enc::`` 前缀则视为明文原样返回。

    Args:
        value: 待解密的字符串

    Returns:
        解密后的明文字符串，或原值
    """
    if value is None or value == "":
        return value
    if not isinstance(value, str) or not value.startswith(_ENCRYPTED_PREFIX):
        return value
    cipher_text = value[len(_ENCRYPTED_PREFIX):]
    return decrypt_sensitive_data(cipher_text)


def encrypt_dict_fields(
    data: dict[str, Any] | None,
    sensitive_keys: list[str] | None = None,
) -> dict[str, Any] | None:
    """加密字典中指定的敏感字段。

    默认敏感字段包括：``password``、``secret``、``token``、``api_key``、
    ``apikey``、``access_key``、``secret_key``、``private_key``。
    字段名匹配不区分大小写。

    Args:
        data: 待加密的字典
        sensitive_keys: 自定义敏感字段名列表，未提供则使用默认列表

    Returns:
        新字典，敏感字段已被加密
    """
    if data is None:
        return None

    if sensitive_keys is None:
        sensitive_keys = [
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "access_key",
            "secret_key",
            "private_key",
        ]

    sensitive_lower = {k.lower() for k in sensitive_keys}
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str) and key.lower() in sensitive_lower:
            result[key] = encrypt_field(value)
        else:
            result[key] = value
    return result


def decrypt_dict_fields(
    data: dict[str, Any] | None,
    sensitive_keys: list[str] | None = None,
) -> dict[str, Any] | None:
    """解密字典中指定的敏感字段。

    与 :func:`encrypt_dict_fields` 对应，仅解密带 ``enc::`` 前缀的字段。

    Args:
        data: 待解密的字典
        sensitive_keys: 自定义敏感字段名列表，未提供则使用默认列表

    Returns:
        新字典，敏感字段已被解密
    """
    if data is None:
        return None

    if sensitive_keys is None:
        sensitive_keys = [
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "access_key",
            "secret_key",
            "private_key",
        ]

    sensitive_lower = {k.lower() for k in sensitive_keys}
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str) and key.lower() in sensitive_lower:
            result[key] = decrypt_field(value)
        else:
            result[key] = value
    return result


def encrypt_json_string(data: str | None) -> str | None:
    """加密 JSON 字符串形式的敏感配置。

    将 JSON 字符串解析为字典，加密敏感字段后重新序列化为 JSON 字符串。

    Args:
        data: JSON 格式的字符串

    Returns:
        加密敏感字段后的 JSON 字符串
    """
    if data is None or data == "":
        return data
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        # 非 JSON 字符串，按普通字符串加密
        return encrypt_field(data)

    if isinstance(parsed, dict):
        encrypted = encrypt_dict_fields(parsed)
        return json.dumps(encrypted, ensure_ascii=False)
    return encrypt_field(data)


def decrypt_json_string(data: str | None) -> str | None:
    """解密 JSON 字符串形式的敏感配置。

    与 :func:`encrypt_json_string` 对应。

    Args:
        data: JSON 格式的字符串

    Returns:
        解密敏感字段后的 JSON 字符串
    """
    if data is None or data == "":
        return data
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return decrypt_field(data)

    if isinstance(parsed, dict):
        decrypted = decrypt_dict_fields(parsed)
        return json.dumps(decrypted, ensure_ascii=False)
    return decrypt_field(data)


__all__ = [
    "decrypt_dict_fields",
    "decrypt_field",
    "decrypt_json_string",
    "encrypt_dict_fields",
    "encrypt_field",
    "encrypt_json_string",
]
