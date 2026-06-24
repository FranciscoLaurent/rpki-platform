"""自动取证与处置闭环数据模型。

包含取证证据、处置动作、事件复盘、通知渠道、通知记录与案例库六类模型，
支撑 RPKI/BGP 路由安全事件的自动取证、处置建议、闭环复盘与通知集成能力。

注意：
    本模块模型不通过 ``app.models.__init__`` 注册（共享文件不可修改），
    使用方需直接 ``from app.models.forensics import ...`` 显式导入。
    Alembic 迁移通过 ``op.create_table`` 显式建表，不依赖 metadata 自动发现。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
# 取证证据
# ──────────────────────────────────────────────


class ForensicEvidence(Base, TimestampMixin, TenantMixin):
    """取证证据模型。

    一条取证证据描述事件发生时刻采集到的快照数据，包含证据类型、内容快照、
    采集时间、采集人与证据来源。证据类型涵盖 ROA/VRP、BGP 样本、AS_PATH、
    传播范围、观察点、资产关系、变更记录与历史基线等。
    """

    __tablename__ = "forensic_evidences"
    __table_args__ = (
        Index("ix_forensic_evidences_incident_id", "incident_id"),
        Index("ix_forensic_evidences_alert_id", "alert_id"),
        Index("ix_forensic_evidences_evidence_type", "evidence_type"),
        Index("ix_forensic_evidences_collected_at", "collected_at"),
        Index("ix_forensic_evidences_collected_by", "collected_by"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联事件 ID",
    )
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联告警 ID",
    )
    evidence_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "证据类型：roa_vrp/bgp_sample/as_path/propagation_scope/"
            "observation_point/asset_relation/change_record/"
            "historical_baseline/other"
        ),
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="证据标题"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="证据描述"
    )
    content: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="证据内容快照（结构化 JSON）"
    )
    source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="证据来源（如 ripe_ris/routeviews/local_collector/manual）",
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="证据采集时间",
    )
    collected_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="采集人用户 ID（自动采集为空）"
    )
    is_auto_collected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否为自动采集",
    )
    integrity_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="证据完整性哈希（用于防篡改校验）",
    )

    def __repr__(self) -> str:
        return (
            f"<ForensicEvidence(id={self.id}, type={self.evidence_type}, "
            f"incident_id={self.incident_id})>"
        )


# ──────────────────────────────────────────────
# 处置动作
# ──────────────────────────────────────────────


class RemediationAction(Base, TimestampMixin, TenantMixin):
    """处置动作模型。

    一条处置动作描述针对事件执行的具体处置步骤，包含动作类型、目标、
    状态、执行人、执行时间与结果。动作类型涵盖联系异常 ASN/上游、
    修正 ROA、调整策略、发布更具体合法前缀、清洗联动与客户通知等。
    """

    __tablename__ = "remediation_actions"
    __table_args__ = (
        Index("ix_remediation_actions_incident_id", "incident_id"),
        Index("ix_remediation_actions_action_type", "action_type"),
        Index("ix_remediation_actions_status", "status"),
        Index("ix_remediation_actions_executed_by", "executed_by"),
        Index("ix_remediation_actions_executed_at", "executed_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联事件 ID",
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "动作类型：contact_asn/contact_upstream/fix_roa/adjust_policy/"
            "announce_legitimate_prefix/scrubber_coordination/"
            "customer_notification/other"
        ),
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="动作标题"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="动作描述"
    )
    target: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="处置目标（如 ASN、前缀、设备名等）",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        comment="优先级：immediate/high/medium/low",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态：pending/in_progress/completed/failed/skipped",
    )
    executed_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="执行人用户 ID"
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行时间"
    )
    result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="执行结果"
    )
    result_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="执行结果详情（结构化 JSON）"
    )
    is_auto_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否为自动生成的建议动作",
    )

    def __repr__(self) -> str:
        return (
            f"<RemediationAction(id={self.id}, type={self.action_type}, "
            f"status={self.status})>"
        )


# ──────────────────────────────────────────────
# 事件复盘
# ──────────────────────────────────────────────


class IncidentReview(Base, TimestampMixin, TenantMixin):
    """事件复盘模型。

    一条复盘记录描述事件关闭后的复盘结论，包含根因分析、经验教训、
    改进措施、复盘人与复盘时间，用于沉淀知识并改进检测与处置流程。
    """

    __tablename__ = "incident_reviews"
    __table_args__ = (
        Index("ix_incident_reviews_incident_id", "incident_id"),
        Index("ix_incident_reviews_reviewed_by", "reviewed_by"),
        Index("ix_incident_reviews_reviewed_at", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联事件 ID",
    )
    root_cause: Mapped[str] = mapped_column(
        Text, nullable=False, comment="根因分析"
    )
    lessons_learned: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="经验教训"
    )
    improvements: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="改进措施"
    )
    prevention_measures: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="预防措施"
    )
    review_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="复盘总结"
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="复盘人用户 ID"
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="复盘时间",
    )
    evidence_preserved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否已保留证据与操作链",
    )
    operation_chain: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="操作链（处置动作时间线）"
    )
    rule_updates: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="沉淀的规则更新建议"
    )

    def __repr__(self) -> str:
        return (
            f"<IncidentReview(id={self.id}, "
            f"incident_id={self.incident_id})>"
        )


# ──────────────────────────────────────────────
# 通知渠道
# ──────────────────────────────────────────────


class NotificationChannel(Base, TimestampMixin, TenantMixin):
    """通知渠道模型。

    描述一个通知投递渠道，包含渠道类型、配置、启用状态与租户隔离。
    支持的渠道类型涵盖 Webhook、邮件、短信、企业微信、钉钉、Slack、
    Teams、PagerDuty 与 ITSM/SOC 集成。
    """

    __tablename__ = "notification_channels"
    __table_args__ = (
        Index("ix_notification_channels_channel_type", "channel_type"),
        Index("ix_notification_channels_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="渠道名称"
    )
    channel_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "渠道类型：webhook/email/sms/wechat_work/dingtalk/slack/"
            "teams/pagerduty/itsm/soc/other"
        ),
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "渠道配置（如 webhook URL、SMTP 配置、API Token 等，"
            "敏感字段应加密存储）"
        ),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="渠道描述"
    )
    severity_filter: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="严重等级过滤（仅通知指定等级，为空表示全部）",
    )
    event_filter: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="事件类型过滤（仅通知指定类型，为空表示全部）",
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationChannel(id={self.id}, "
            f"type={self.channel_type}, enabled={self.enabled})>"
        )


# ──────────────────────────────────────────────
# 通知记录
# ──────────────────────────────────────────────


class NotificationLog(Base, TimestampMixin):
    """通知记录模型。

    一条通知记录描述一次通知投递的完整信息，包含关联事件、渠道、
    内容、状态与发送时间，用于通知审计与重试。
    """

    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notification_logs_incident_id", "incident_id"),
        Index("ix_notification_logs_channel_id", "channel_id"),
        Index("ix_notification_logs_status", "status"),
        Index("ix_notification_logs_sent_at", "sent_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联事件 ID",
    )
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联通知渠道 ID",
    )
    channel_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="渠道类型（冗余存储便于查询）"
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="通知标题"
    )
    content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="通知内容"
    )
    content_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="通知内容详情（结构化 JSON）"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态：pending/sent/failed/retry",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="失败错误信息"
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发送时间"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="重试次数"
    )
    triggered_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="触发人用户 ID（自动触发为空）"
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog(id={self.id}, "
            f"channel_type={self.channel_type}, status={self.status})>"
        )


# ──────────────────────────────────────────────
# 案例库
# ──────────────────────────────────────────────


class CaseLibrary(Base, TimestampMixin, TenantMixin):
    """案例库模型。

    一条案例记录描述一个典型事件的处置经验沉淀，包含标题、描述、根因、
    处置方案、标签与关联事件，用于知识复用与培训。
    """

    __tablename__ = "case_library"
    __table_args__ = (
        Index("ix_case_library_title", "title"),
        Index("ix_case_library_severity", "severity"),
        Index("ix_case_library_is_published", "is_published"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="案例标题"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="案例描述"
    )
    root_cause: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="根因分析"
    )
    remediation_plan: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="处置方案"
    )
    tags: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="标签列表"
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="P3",
        comment="严重等级：P0/P1/P2/P3/P4",
    )
    incident_ids: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="关联事件 ID 列表"
    )
    alert_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="关联告警类型"
    )
    affected_prefixes: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="受影响前缀列表"
    )
    affected_asns: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="受影响 ASN 列表"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否已发布（发布后可被检索复用）",
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="创建人用户 ID"
    )

    def __repr__(self) -> str:
        return (
            f"<CaseLibrary(id={self.id}, title={self.title}, "
            f"severity={self.severity})>"
        )


__all__ = [
    "CaseLibrary",
    "ForensicEvidence",
    "IncidentReview",
    "NotificationChannel",
    "NotificationLog",
    "RemediationAction",
]
