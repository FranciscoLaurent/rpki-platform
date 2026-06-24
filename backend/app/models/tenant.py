"""租户模型：多租户组织与成员关系。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(Base, TimestampMixin):
    """租户（组织）模型。"""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="租户名称")
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="租户短标识"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", comment="租户状态"
    )
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="租户配置")
    max_users: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, comment="最大用户数"
    )

    # 关联成员
    members: Mapped[list[TenantMember]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug={self.slug})>"


class TenantMember(Base, TimestampMixin):
    """租户成员关联模型，记录用户在租户内的角色。"""

    __tablename__ = "tenant_members"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_tenant_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="member", comment="租户内角色"
    )

    # 关联关系
    tenant: Mapped[Tenant] = relationship(back_populates="members")
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return (
            f"<TenantMember(user_id={self.user_id}, tenant_id={self.tenant_id}, role={self.role})>"
        )
