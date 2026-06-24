"""字段级加密工具。

提供 SQLAlchemy TypeDecorator，自动对敏感字段进行加密/解密。
基于 Fernet 对称加密（AES-128-CBC + HMAC-SHA256），密钥来自
``settings.FIELD_ENCRYPTION_KEY``（或回退到 ``ENCRYPTION_KEY``/``SECRET_KEY``）。

使用方式::

    from app.core.field_encryption import EncryptedJSON

    class IntegrationConfig(Base):
        auth_config: Mapped[dict | None] = mapped_column(
            EncryptedJSON, nullable=True
        )

写入时自动加密，读取时自动解密，业务代码无感知。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, TypeDecorator
from sqlalchemy.engine import Dialect

from app.core.logging import get_logger
from app.core.security import decrypt_field, encrypt_field

logger = get_logger("app.core.field_encryption")


class EncryptedString(TypeDecorator):
    """加密字符串类型。

    在数据库中以密文形式存储，Python 层以明文字符串形式使用。
    写入时自动加密，读取时自动解密。

    适用场景：密码、Token、API Key 等敏感字符串字段。
    """

    impl = JSON
    cache_ok = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """初始化加密字符串类型。"""
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """写入数据库前加密。"""
        if value is None:
            return None
        try:
            return encrypt_field(value)
        except Exception:
            logger.error("字段加密失败，写入原始值", exc_info=True)
            return value if isinstance(value, str) else str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        """从数据库读取后解密。"""
        if value is None:
            return None
        return decrypt_field(value)


class EncryptedJSON(TypeDecorator):
    """加密 JSON 类型。

    在数据库中以密文字符串形式存储 JSON 数据，Python 层以字典/列表形式使用。
    写入时先 JSON 序列化再加密，读取时先解密再 JSON 反序列化。

    适用场景：集成配置的 ``auth_config``、含敏感信息的嵌套结构等。

    Note:
        底层使用 ``JSON`` 类型作为 impl，但实际存储的是加密字符串。
        在 PostgreSQL 中建议配合 ``Text`` 列类型使用，或在迁移时
        将列类型改为 ``TEXT``。此处使用 ``JSON`` 以保持与现有模型
        的兼容性，实际加密后的密文以字符串形式存储。
    """

    impl = JSON
    cache_ok = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """初始化加密 JSON 类型。"""
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """写入数据库前加密。"""
        if value is None:
            return None
        try:
            return encrypt_field(value)
        except Exception:
            logger.error("JSON 字段加密失败，写入原始值", exc_info=True)
            return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """从数据库读取后解密。"""
        if value is None:
            return None
        return decrypt_field(value)


__all__ = [
    "EncryptedJSON",
    "EncryptedString",
]
