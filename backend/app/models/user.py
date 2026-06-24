"""用户、角色、权限模型及关联表。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


# ──────────────────────────────────────────────
# 关联表
# ──────────────────────────────────────────────

# 角色-权限 多对多关联
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# 用户-角色 多对多关联
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base, TimestampMixin):
    """用户模型。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True, comment="邮箱地址"
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="用户名"
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="姓名")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否超级管理员"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", comment="用户状态"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后登录时间"
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="连续登录失败次数"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="锁定截止时间"
    )
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="MFA 密钥")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否需要强制修改密码",
    )

    # 关联角色
    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles, back_populates="users", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"


class Role(Base, TimestampMixin):
    """角色模型。"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="角色名称")
    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="角色编码"
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="角色描述")
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否系统内置角色（不可删除）",
    )

    # 关联
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, code={self.code})>"


class Permission(Base, TimestampMixin):
    """权限模型。"""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="权限名称")
    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="权限编码"
    )
    resource: Mapped[str] = mapped_column(String(100), nullable=False, comment="资源类型")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="动作类型")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="权限描述")

    # 关联
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, code={self.code})>"
