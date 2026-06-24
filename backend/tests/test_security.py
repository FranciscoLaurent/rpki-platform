"""安全功能测试：密码哈希、JWT 令牌、字段加密。

覆盖 ``app.core.security`` 与 ``app.core.field_encryption`` 模块。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.fernet import InvalidToken

from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_field,
    decrypt_sensitive_data,
    encrypt_field,
    encrypt_sensitive_data,
    get_password_hash,
    verify_password,
    verify_token_with_rotation,
)

# ──────────────────────────────────────────────
# 密码哈希与验证
# ──────────────────────────────────────────────


def test_password_hash_is_not_plaintext() -> None:
    """密码哈希值不应等于明文。"""
    plain = "my-secret-password"
    hashed = get_password_hash(plain)
    assert hashed != plain
    assert len(hashed) > 0


def test_password_hash_is_unique_per_call() -> None:
    """同一密码每次哈希结果应不同（bcrypt 使用随机盐）。"""
    plain = "same-password"
    hash1 = get_password_hash(plain)
    hash2 = get_password_hash(plain)
    assert hash1 != hash2


def test_verify_password_correct() -> None:
    """正确密码应通过验证。"""
    plain = "correct-password"
    hashed = get_password_hash(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_incorrect() -> None:
    """错误密码应不通过验证。"""
    plain = "correct-password"
    hashed = get_password_hash(plain)
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_empty() -> None:
    """空密码应能正常处理（不抛异常）。"""
    hashed = get_password_hash("nonempty")
    assert verify_password("", hashed) is False


# ──────────────────────────────────────────────
# JWT 生成与验证
# ──────────────────────────────────────────────


def test_create_and_decode_access_token() -> None:
    """生成的 JWT 应能被正确解码。"""
    token = create_access_token(subject=42)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert "exp" in payload
    assert "iat" in payload


def test_access_token_with_extra_claims() -> None:
    """JWT 应支持附加自定义声明。"""
    token = create_access_token(
        subject="user-1",
        extra_claims={"role": "admin", "tenant_id": 7},
    )
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"
    assert payload["tenant_id"] == 7


def test_access_token_with_custom_expiry() -> None:
    """JWT 应支持自定义过期时间。"""
    token = create_access_token(subject=1, expires_delta=timedelta(seconds=1))
    payload = decode_access_token(token)
    assert payload is not None
    assert "exp" in payload


def test_decode_invalid_token_returns_none() -> None:
    """无效 JWT 应返回 None。"""
    assert decode_access_token("not-a-valid-token") is None


def test_decode_tampered_token_returns_none() -> None:
    """被篡改的 JWT 应返回 None。"""
    token = create_access_token(subject=1)
    # 篡改最后几个字符
    tampered = token[:-4] + "AAAA"
    assert decode_access_token(tampered) is None


def test_verify_token_with_rotation_uses_current_key() -> None:
    """verify_token_with_rotation 应能验证当前密钥签发的令牌。"""
    token = create_access_token(subject=99)
    payload = verify_token_with_rotation(token)
    assert payload is not None
    assert payload["sub"] == "99"


def test_verify_token_with_rotation_returns_none_for_invalid() -> None:
    """无效令牌应返回 None。"""
    assert verify_token_with_rotation("invalid-token") is None


# ──────────────────────────────────────────────
# 敏感数据加密与解密
# ──────────────────────────────────────────────


def test_encrypt_and_decrypt_sensitive_data() -> None:
    """敏感数据加密后应能正确解密还原。"""
    plaintext = "sensitive-api-key-12345"
    encrypted = encrypt_sensitive_data(plaintext)
    assert encrypted != plaintext
    decrypted = decrypt_sensitive_data(encrypted)
    assert decrypted == plaintext


def test_encrypt_produces_different_ciphertext() -> None:
    """同一明文每次加密结果应不同（Fernet 使用随机 IV）。"""
    plaintext = "same-secret"
    enc1 = encrypt_sensitive_data(plaintext)
    enc2 = encrypt_sensitive_data(plaintext)
    assert enc1 != enc2
    # 但都能解密为同一明文
    assert decrypt_sensitive_data(enc1) == plaintext
    assert decrypt_sensitive_data(enc2) == plaintext


def test_decrypt_invalid_ciphertext_raises() -> None:
    """无效密文解密应抛出 InvalidToken。"""
    with pytest.raises(InvalidToken):
        decrypt_sensitive_data("not-valid-ciphertext")


# ──────────────────────────────────────────────
# 字段级加密与解密
# ──────────────────────────────────────────────


def test_encrypt_and_decrypt_string_field() -> None:
    """字符串字段加密后应能正确解密。"""
    original = "field-value-42"
    encrypted = encrypt_field(original)
    assert encrypted != original
    decrypted = decrypt_field(encrypted)
    assert decrypted == original


def test_encrypt_field_none_returns_none() -> None:
    """None 输入应返回 None。"""
    assert encrypt_field(None) is None


def test_decrypt_field_none_returns_none() -> None:
    """None 输入应返回 None。"""
    assert decrypt_field(None) is None


def test_encrypt_and_decrypt_dict_field() -> None:
    """字典字段加密后应能正确解密为字典。"""
    original = {"key": "value", "nested": {"a": 1}}
    encrypted = encrypt_field(original)
    assert isinstance(encrypted, str)
    decrypted = decrypt_field(encrypted)
    assert decrypted == original


def test_encrypt_and_decrypt_list_field() -> None:
    """列表字段加密后应能正确解密为列表。"""
    original = [1, 2, 3, "four"]
    encrypted = encrypt_field(original)
    decrypted = decrypt_field(encrypted)
    assert decrypted == original


def test_decrypt_field_invalid_ciphertext_returns_original() -> None:
    """无效密文应返回原始输入（不抛异常，保证业务连续性）。"""
    invalid = "not-a-valid-ciphertext"
    result = decrypt_field(invalid)
    # 解密失败时返回原始值
    assert result == invalid


def test_decrypt_field_empty_string_returns_empty() -> None:
    """空字符串应原样返回。"""
    assert decrypt_field("") == ""


# ──────────────────────────────────────────────
# 加密密钥一致性
# ──────────────────────────────────────────────


def test_field_encryption_uses_stable_key() -> None:
    """字段加密密钥应稳定（同一进程内多次调用结果一致）。"""
    plaintext = "stable-key-test"
    enc1 = encrypt_field(plaintext)
    enc2 = encrypt_field(plaintext)
    # 密文不同（随机 IV），但都能解密
    assert decrypt_field(enc1) == plaintext
    assert decrypt_field(enc2) == plaintext
