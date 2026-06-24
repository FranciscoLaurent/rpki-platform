"""审计日志模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """审计日志模型，记录用户关键操作。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="操作用户 ID"
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="租户 ID"
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="操作动作"
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="资源类型"
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="资源 ID"
    )
    details: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="操作详情"
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="IP 地址"
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="User-Agent"
    )
    request_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="请求追踪 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间",
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action})>"
