"""ROA 变更审批数据模型。

包含 ROA 变更请求与审批规则两类模型，支撑 ROA 高级管理能力：
审批控制与变更后验证。

设计要点：
- 变更请求记录完整的变更前后状态，支持回滚
- 审批规则支持自动批准、单人审批、双人审批、委员会审批四种流程
- 高风险变更（核心前缀、大规模影响）强制审批
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class ROAChangeRequest(Base, TimestampMixin, TenantMixin):
    """ROA 变更请求模型。

    记录一次 ROA 变更的完整生命周期：创建 → 审批 → 执行 → 验证 → （可选）回滚。

    变更类型：
    - create：创建新 ROA
    - modify：修改现有 ROA 的 prefix/origin_as/max_length
    - revoke：撤销现有 ROA

    状态流转：
    - draft → pending_approval → approved → executed → rolled_back
    - pending_approval → rejected
    - approved → failed（执行失败）
    """

    __tablename__ = "roa_change_requests"
    __table_args__ = (
        Index("ix_roa_change_requests_change_type", "change_type"),
        Index("ix_roa_change_requests_roa_id", "roa_id"),
        Index("ix_roa_change_requests_status", "status"),
        Index("ix_roa_change_requests_risk_level", "risk_level"),
        Index("ix_roa_change_requests_requested_by", "requested_by"),
        Index("ix_roa_change_requests_approved_by", "approved_by"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="变更类型：create/modify/revoke",
    )
    roa_id: Mapped[int | None] = mapped_column(
        ForeignKey("roas.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的 ROA ID（修改/撤销时填写）",
    )

    # 变更后的值
    prefix: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="变更后的前缀"
    )
    origin_as: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="变更后的起源 AS 号"
    )
    max_length: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="变更后的最大前缀长度"
    )

    # 变更前的值（修改/撤销时记录，用于回滚）
    current_prefix: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="变更前的前缀"
    )
    current_origin_as: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="变更前的起源 AS 号"
    )
    current_max_length: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="变更前的最大前缀长度"
    )

    # 变更原因与影响评估
    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="变更原因"
    )
    impact_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="影响评估摘要（JSON）"
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="low",
        comment="风险等级：low/medium/high/critical",
    )

    # 审批状态与流程
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending_approval",
        comment=(
            "状态：draft/pending_approval/approved/rejected/"
            "executed/failed/rolled_back"
        ),
    )
    approval_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("roa_approval_rules.id", ondelete="SET NULL"),
        nullable=True,
        comment="匹配的审批规则 ID",
    )
    required_approvals: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="所需审批人数（由审批规则决定）",
    )
    approvals: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="审批记录列表（含审批人、动作、意见、时间）",
    )

    # 申请人与审批人
    requested_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="申请人 ID",
    )
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="最终审批人 ID",
    )
    approval_comments: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="审批意见"
    )

    # 执行信息
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行时间"
    )
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="执行结果（JSON）"
    )

    # 回滚信息
    rollback_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="回滚信息（JSON）"
    )

    def __repr__(self) -> str:
        return (
            f"<ROAChangeRequest(id={self.id}, type={self.change_type}, "
            f"status={self.status}, risk={self.risk_level})>"
        )


class ROAApprovalRule(Base, TimestampMixin, TenantMixin):
    """ROA 审批规则模型。

    定义 ROA 变更的审批流程，根据变更类型、前缀重要性、风险等级等条件
    匹配适用的审批流程。

    审批类型：
    - auto_approve：自动批准（无需人工审批）
    - single_approval：单人审批
    - dual_approval：双人审批（两人都需批准）
    - committee：委员会审批（多人中多数批准）
    """

    __tablename__ = "roa_approval_rules"
    __table_args__ = (
        Index("ix_roa_approval_rules_rule_type", "rule_type"),
        Index("ix_roa_approval_rules_enabled", "enabled"),
        Index("ix_roa_approval_rules_priority", "priority"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="规则名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="规则描述"
    )
    rule_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment=(
            "审批类型：auto_approve/single_approval/"
            "dual_approval/committee"
        ),
    )
    conditions: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "触发条件（JSON），如 "
            '{"change_type": ["revoke"], "prefix_importance": ["critical"], '
            '"risk_level": ["high", "critical"]}'
        ),
    )
    approvers: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="审批人 ID 列表",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="优先级（数值越小优先级越高）",
    )

    def __repr__(self) -> str:
        return (
            f"<ROAApprovalRule(id={self.id}, name={self.name}, "
            f"type={self.rule_type})>"
        )


__all__ = [
    "ROAApprovalRule",
    "ROAChangeRequest",
]
