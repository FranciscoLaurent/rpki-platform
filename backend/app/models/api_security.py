"""API 安全相关数据模型。

包含服务账号、API 密钥、OAuth2 客户端/授权码/令牌与 API 限流策略模型，
支撑 REST/gRPC API 的认证、授权、限流与审计能力。

注意：
    本模块的模型不通过 ``app.models.__init__`` 自动注册（共享文件不可修改），
    使用方需显式导入。Alembic 迁移 ``0011_api_security_models`` 显式建表。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


# ──────────────────────────────────────────────
# 服务账号
# ──────────────────────────────────────────────


class ServiceAccount(Base, TimestampMixin):
    """服务账号模型。

    用于 API 集成场景的非交互式身份，可关联多个 API Key 与 OAuth2 客户端，
    并可绑定 RBAC 角色以实现细粒度权限控制。
    """

    __tablename__ = "service_accounts"
    __table_args__ = (
        Index("ix_service_accounts_tenant_id", "tenant_id"),
        Index("ix_service_accounts_status", "status"),
        Index("ix_service_accounts_name", "name"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="服务账号名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="服务账号描述"
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="所属租户 ID"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/disabled/expired",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后使用时间"
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="创建者用户 ID",
    )
    # 关联角色码列表（不通过外键关联 roles 表，避免与 RBAC 强耦合）
    role_codes: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list, comment="绑定的角色编码列表"
    )
    allowed_scopes: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list, comment="允许的权限范围列表"
    )

    # 关联 API 密钥
    api_keys: Mapped[list["APIKey"]] = relationship(
        back_populates="service_account",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ServiceAccount(id={self.id}, name={self.name})>"


# ──────────────────────────────────────────────
# API 密钥
# ──────────────────────────────────────────────


class APIKey(Base, TimestampMixin):
    """API 密钥模型。

    每个密钥关联一个服务账号，存储密钥哈希值与前缀展示信息，
    支持权限范围、过期时间与使用统计。
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_service_account_id", "service_account_id"),
        Index("ix_api_keys_prefix", "key_prefix"),
        Index("ix_api_keys_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    service_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("service_accounts.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属服务账号 ID",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密钥名称（用于识别）"
    )
    key_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密钥哈希值（bcrypt）"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="密钥前缀（用于展示与识别）"
    )
    scopes: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list, comment="权限范围列表"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后使用时间"
    )
    last_used_ip: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="最后使用 IP 地址"
    )
    use_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="使用次数"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/revoked/expired",
    )

    # 关联服务账号
    service_account: Mapped["ServiceAccount"] = relationship(
        back_populates="api_keys"
    )

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"


# ──────────────────────────────────────────────
# OAuth2 客户端
# ──────────────────────────────────────────────


class OAuth2Client(Base, TimestampMixin):
    """OAuth2 客户端模型。

    支持授权码模式（authorization_code）、客户端凭据模式（client_credentials）
    与刷新令牌模式（refresh_token）。
    """

    __tablename__ = "oauth2_clients"
    __table_args__ = (
        Index("ix_oauth2_clients_client_id", "client_id"),
        Index("ix_oauth2_clients_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    client_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        comment="客户端 ID（公开标识）",
    )
    client_secret_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="客户端密钥哈希（公开客户端为空）"
    )
    client_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="客户端名称"
    )
    client_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="confidential",
        comment="客户端类型：confidential/public",
    )
    redirect_uris: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, comment="允许的回调 URI 列表"
    )
    scopes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, comment="允许的权限范围列表"
    )
    grant_types: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="授权类型列表：authorization_code/client_credentials/refresh_token",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/disabled",
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="所属租户 ID"
    )

    # 关联授权码与令牌
    authorization_codes: Mapped[list["OAuth2AuthorizationCode"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )
    tokens: Mapped[list["OAuth2Token"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<OAuth2Client(id={self.id}, client_id={self.client_id})>"


# ──────────────────────────────────────────────
# OAuth2 授权码
# ──────────────────────────────────────────────


class OAuth2AuthorizationCode(Base, TimestampMixin):
    """OAuth2 授权码模型。

    用于授权码模式中临时存储用户授权决策，使用后即失效。
    """

    __tablename__ = "oauth2_authorization_codes"
    __table_args__ = (
        Index("ix_oauth2_auth_codes_code", "code"),
        Index("ix_oauth2_auth_codes_user_id", "user_id"),
        Index("ix_oauth2_auth_codes_client_id", "client_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    code: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="授权码（一次性使用）",
    )
    client_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联 OAuth2 客户端 ID",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="授权用户 ID",
    )
    scope: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="授权范围（空格分隔）"
    )
    redirect_uri: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="回调 URI"
    )
    code_challenge: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="PKCE code_challenge"
    )
    code_challenge_method: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="PKCE 方法：plain/S256"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="过期时间"
    )
    used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否已使用"
    )

    # 关联
    client: Mapped["OAuth2Client"] = relationship(
        back_populates="authorization_codes"
    )

    def __repr__(self) -> str:
        return f"<OAuth2AuthorizationCode(id={self.id}, client_id={self.client_id})>"


# ──────────────────────────────────────────────
# OAuth2 令牌
# ──────────────────────────────────────────────


class OAuth2Token(Base, TimestampMixin):
    """OAuth2 令牌模型。

    存储 access_token 与 refresh_token，关联用户与客户端。
    """

    __tablename__ = "oauth2_tokens"
    __table_args__ = (
        Index("ix_oauth2_tokens_access_token", "access_token"),
        Index("ix_oauth2_tokens_refresh_token", "refresh_token"),
        Index("ix_oauth2_tokens_user_id", "user_id"),
        Index("ix_oauth2_tokens_client_id", "client_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    access_token: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
        comment="访问令牌（哈希存储）",
    )
    refresh_token: Mapped[str | None] = mapped_column(
        String(512),
        unique=True,
        nullable=True,
        comment="刷新令牌（哈希存储）",
    )
    client_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联 OAuth2 客户端 ID",
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联用户 ID（客户端凭据模式为空）",
    )
    service_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("service_accounts.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联服务账号 ID（客户端凭据模式）",
    )
    scope: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="授权范围（空格分隔）"
    )
    token_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Bearer",
        comment="令牌类型",
    )
    expires_in: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, comment="有效期（秒）"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="过期时间"
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否已撤销"
    )

    # 关联
    client: Mapped["OAuth2Client"] = relationship(back_populates="tokens")

    def __repr__(self) -> str:
        return f"<OAuth2Token(id={self.id}, client_id={self.client_id})>"


# ──────────────────────────────────────────────
# API 限流策略
# ──────────────────────────────────────────────


class APIThrottlePolicy(Base, TimestampMixin):
    """API 限流策略模型。

    基于角色或服务账号配置请求上限与时间窗口，可按路径模式匹配。
    限流实际执行依赖 Redis 令牌桶算法（见 ``app.core.api_throttle``）。
    """

    __tablename__ = "api_throttle_policies"
    __table_args__ = (
        Index("ix_api_throttle_policies_role_code", "role_code"),
        Index("ix_api_throttle_policies_service_account_id", "service_account_id"),
        Index("ix_api_throttle_policies_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="策略名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="策略描述"
    )
    # 关联主体（二选一，均为空表示全局策略）
    role_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="关联角色编码"
    )
    service_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("service_accounts.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联服务账号 ID",
    )
    # 限流参数
    request_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="请求上限"
    )
    window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, comment="时间窗口（秒）"
    )
    path_pattern: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="路径模式（正则，为空匹配全部）"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="所属租户 ID"
    )

    def __repr__(self) -> str:
        return (
            f"<APIThrottlePolicy(id={self.id}, name={self.name}, "
            f"limit={self.request_limit}/{self.window_seconds}s)>"
        )


__all__ = [
    "APIKey",
    "APIThrottlePolicy",
    "OAuth2AuthorizationCode",
    "OAuth2Client",
    "OAuth2Token",
    "ServiceAccount",
]
