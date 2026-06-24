"""API Key 数据模型。

提供基于用户的 API Key 认证凭证，支持权限范围（scopes）、
过期时间与使用统计。密钥哈希存储，明文仅在创建时返回一次。

注意：
    本模型不通过 ``app.models.__init__`` 自动注册（共享文件不可修改），
    使用方需显式导入。Alembic 迁移 ``0010_api_key_models`` 显式建表。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ApiKey(Base, TimestampMixin, TenantMixin):
    """API 密钥模型。

    每个密钥关联一个用户，存储密钥哈希值与前缀展示信息，
    支持权限范围（scopes）、过期时间与最后使用统计。
    明文密钥仅在创建时返回一次，后续仅通过哈希比对验证。
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_key_prefix", "key_prefix"),
        Index("ix_api_keys_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="密钥名称（用于识别）")
    key_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密钥哈希值（bcrypt）"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="密钥前缀（用于展示与识别）"
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属用户 ID",
    )
    scopes: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list, comment="权限范围列表"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后使用时间"
    )

    # 关联用户
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"


__all__ = ["ApiKey"]
