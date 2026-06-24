"""ROA 良性冲突相关数据模型。

包含良性冲突记录、维护窗口、清洗商授权与 Anycast 节点登记四类模型，
支撑 ROA 良性冲突识别引擎的证据治理、授权管理与误报抑制能力。

注意：
    本模块模型不通过 ``app.models.__init__`` 注册（共享文件不可修改），
    使用方需直接 ``from app.models.benign_conflict import ...`` 显式导入。
    Alembic 迁移通过 ``op.create_table`` 显式建表，不依赖 metadata 自动发现。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


# ──────────────────────────────────────────────
# 良性冲突记录
# ──────────────────────────────────────────────


class BenignConflictRecord(Base, TimestampMixin, TenantMixin):
    """良性冲突记录模型。

    一条良性冲突记录描述一个被识别为良性（非恶意）的 ROA/BGP 冲突实例，
    包含冲突类型、置信度、证据、处理建议、状态与授权时间窗等信息。
    可选关联告警 ID，用于回溯原始告警。
    """

    __tablename__ = "benign_conflict_records"
    __table_args__ = (
        Index("ix_benign_conflict_records_alert_id", "alert_id"),
        Index("ix_benign_conflict_records_conflict_type", "conflict_type"),
        Index("ix_benign_conflict_records_prefix", "prefix"),
        Index("ix_benign_conflict_records_origin_as", "origin_as"),
        Index("ix_benign_conflict_records_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联告警 ID",
    )
    conflict_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "冲突类型：ddos_scrubbing/anycast_expansion/planned_maintenance/"
            "resource_transfer/data_source_delay/customer_misconfig"
        ),
    )
    prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="关联的网络前缀"
    )
    origin_as: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="观测到的起源 AS 号"
    )
    expected_origin_as: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="期望的起源 AS 号（资产台账/ROA 授权）"
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="置信度（0-1）",
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="证据数据"
    )
    recommendation: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="处理建议"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="suspected",
        comment="状态：suspected/confirmed/dismissed",
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="授权时间窗结束时间",
    )
    related_work_order: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="关联工单号"
    )

    def __repr__(self) -> str:
        return (
            f"<BenignConflictRecord(id={self.id}, "
            f"type={self.conflict_type}, prefix={self.prefix})>"
        )


# ──────────────────────────────────────────────
# 维护窗口
# ──────────────────────────────────────────────


class MaintenanceWindow(Base, TimestampMixin, TenantMixin):
    """维护窗口模型。

    描述一个计划内维护窗口，包含起止时间、受影响前缀与 ASN 列表、
    审批人与关联工单号，用于识别计划内割接导致的良性冲突。
    """

    __tablename__ = "maintenance_windows"
    __table_args__ = (
        Index("ix_maintenance_windows_status", "status"),
        Index("ix_maintenance_windows_start_time", "start_time"),
        Index("ix_maintenance_windows_end_time", "end_time"),
        Index("ix_maintenance_windows_work_order_id", "work_order_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="维护窗口名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="维护描述"
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="开始时间"
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="结束时间"
    )
    prefixes: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="受影响前缀列表"
    )
    asns: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="受影响 ASN 列表"
    )
    approved_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="审批人用户 ID"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="scheduled",
        comment="状态：scheduled/active/completed/cancelled",
    )
    work_order_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="关联工单号"
    )

    def __repr__(self) -> str:
        return (
            f"<MaintenanceWindow(id={self.id}, name={self.name}, "
            f"status={self.status})>"
        )


# ──────────────────────────────────────────────
# 清洗商授权
# ──────────────────────────────────────────────


class ScrubberAuthorization(Base, TimestampMixin, TenantMixin):
    """清洗商授权模型。

    记录清洗商 AS 对客户前缀的临时宣告授权，包含授权起止时间、
    关联工单号与联系人信息，用于识别 DDoS 清洗临时宣告导致的良性冲突。
    """

    __tablename__ = "scrubber_authorizations"
    __table_args__ = (
        Index(
            "ix_scrubber_authorizations_scrubber_asn",
            "scrubber_asn",
        ),
        Index(
            "ix_scrubber_authorizations_customer_prefix",
            "customer_prefix",
        ),
        Index(
            "ix_scrubber_authorizations_customer_asn",
            "customer_asn",
        ),
        Index("ix_scrubber_authorizations_status", "status"),
        Index("ix_scrubber_authorizations_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    scrubber_asn: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="清洗商 AS 号"
    )
    customer_prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="客户前缀（CIDR）"
    )
    customer_asn: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="客户 AS 号"
    )
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="授权时间"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="授权截止时间"
    )
    work_order_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="关联工单号"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/expired/revoked",
    )
    contact_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="联系人信息"
    )

    def __repr__(self) -> str:
        return (
            f"<ScrubberAuthorization(id={self.id}, "
            f"scrubber_asn={self.scrubber_asn}, "
            f"customer_prefix={self.customer_prefix})>"
        )


# ──────────────────────────────────────────────
# Anycast 节点登记
# ──────────────────────────────────────────────


class AnycastNode(Base, TimestampMixin, TenantMixin):
    """Anycast 节点登记模型。

    记录 Anycast 节点的 AS、前缀、地域、机房与业务标签，
    用于识别 Anycast 扩容导致的多 origin 良性冲突。
    """

    __tablename__ = "anycast_nodes"
    __table_args__ = (
        Index("ix_anycast_nodes_node_asn", "node_asn"),
        Index("ix_anycast_nodes_prefix", "prefix"),
        Index("ix_anycast_nodes_status", "status"),
        Index("ix_anycast_nodes_region", "region"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    node_asn: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Anycast 节点 AS 号"
    )
    prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Anycast 前缀（CIDR）"
    )
    region: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="地域"
    )
    site: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="机房"
    )
    business_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="业务标签"
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="登记时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/inactive",
    )

    def __repr__(self) -> str:
        return (
            f"<AnycastNode(id={self.id}, node_asn={self.node_asn}, "
            f"prefix={self.prefix})>"
        )


__all__ = [
    "AnycastNode",
    "BenignConflictRecord",
    "MaintenanceWindow",
    "ScrubberAuthorization",
]
