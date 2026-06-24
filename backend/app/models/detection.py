"""BGP 路由安全检测引擎数据模型。

包含检测规则、告警、事件与风险评分四类核心模型，支撑 BGP 路由安全检测引擎
的规则匹配、告警生成、事件归并与可解释风险评分能力。
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

# ──────────────────────────────────────────────
# 检测规则
# ──────────────────────────────────────────────


class DetectionRule(Base, TimestampMixin, TenantMixin):
    """检测规则模型。

    描述一条 BGP 路由安全检测规则，包含规则类型、生效条件、阈值、白名单与
    生效范围。规则引擎在评估 BGP 公告时按 ``rule_type`` 调用对应检测器。
    """

    __tablename__ = "detection_rules"
    __table_args__ = (
        Index("ix_detection_rules_rule_type", "rule_type"),
        Index("ix_detection_rules_enabled", "enabled"),
        Index("ix_detection_rules_priority", "priority"),
        Index("ix_detection_rules_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="规则名称")
    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="规则唯一编码，用于幂等初始化",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="规则描述")
    rule_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "规则类型：hijack/subprefix_hijack/moas/route_leak/"
            "path_anomaly/withdraw_flap/rpki_invalid"
        ),
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
    conditions: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="规则条件配置"
    )
    thresholds: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="阈值配置"
    )
    whitelist: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="白名单配置（前缀/ASN/观察点）"
    )
    scope: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="生效范围（前缀列表、ASN 列表等）"
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="P3",
        comment="严重等级：P0/P1/P2/P3/P4",
    )

    # 关联告警
    alerts: Mapped[list[Alert]] = relationship(back_populates="rule", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DetectionRule(id={self.id}, code={self.code}, type={self.rule_type})>"


# ──────────────────────────────────────────────
# 告警
# ──────────────────────────────────────────────


class Alert(Base, TimestampMixin, TenantMixin):
    """告警模型。

    一条告警由检测规则触发，描述一个具体的路由安全事件实例，包含证据、
    风险评分、置信度与处置状态。多条同源告警可归并到同一事件。
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_rule_id", "rule_id"),
        Index("ix_alerts_prefix", "prefix"),
        Index("ix_alerts_origin_as", "origin_as"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_incident_id", "incident_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("detection_rules.id", ondelete="SET NULL"),
        nullable=True,
        comment="触发的规则 ID",
    )
    alert_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="告警类型，与规则 rule_type 对应",
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="P3",
        comment="严重等级：P0/P1/P2/P3/P4",
    )
    prefix: Mapped[str] = mapped_column(String(64), nullable=False, comment="关联的网络前缀")
    origin_as: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="关联的起源 AS 号"
    )
    as_path: Mapped[list[int] | None] = mapped_column(JSON, nullable=True, comment="AS 路径列表")
    observation_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("observation_points.id", ondelete="SET NULL"),
        nullable=True,
        comment="观察点 ID",
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="告警标题")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="告警描述")
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="证据数据")
    risk_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="风险评分（0-100）"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="置信度（0-1）"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="new",
        comment=("处置状态：new/confirmed/assigned/resolved/closed/false_positive"),
    )
    is_benign_conflict: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否为良性冲突（如授权多 origin）",
    )
    benign_conflict_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="良性冲突类型：authorized_multi_origin/anycast/managed/scrubber",
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联事件 ID",
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次发现时间"
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近发现时间"
    )

    # 关联
    rule: Mapped[DetectionRule | None] = relationship(back_populates="alerts")
    risk_scores: Mapped[list[RiskScore]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id}, type={self.alert_type}, "
            f"prefix={self.prefix}, severity={self.severity})>"
        )


# ──────────────────────────────────────────────
# 事件
# ──────────────────────────────────────────────


class Incident(Base, TimestampMixin, TenantMixin):
    """事件模型。

    一个事件聚合多条同源告警，描述一个完整的安全事件，包含分派、根因、
    处置结论与时间线。
    """

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_assigned_to", "assigned_to"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="事件标题")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="事件描述")
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="P3",
        comment="严重等级：P0/P1/P2/P3/P4",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment=("事件状态：open/investigating/mitigating/resolved/closed"),
    )
    alert_ids: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="关联告警 ID 列表"
    )
    affected_prefixes: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="受影响前缀列表"
    )
    affected_asns: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="受影响 ASN 列表"
    )
    assigned_to: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="分派给的用户 ID",
    )
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True, comment="根因分析")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True, comment="处置结论")
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="事件证据")
    timeline: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="事件时间线"
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次发现时间"
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近发现时间"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="解决时间"
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="关闭时间"
    )

    def __repr__(self) -> str:
        return f"<Incident(id={self.id}, title={self.title}, status={self.status})>"


# ──────────────────────────────────────────────
# 风险评分
# ──────────────────────────────────────────────


class RiskScore(Base, TimestampMixin):
    """风险评分模型。

    存储告警或事件的可解释风险评分，按六个维度分解：资产重要性、RPKI 证据、
    BGP 传播、授权与变更、历史基线、外部风险。每个维度包含评分与因素明细。
    """

    __tablename__ = "risk_scores"
    __table_args__ = (
        Index("ix_risk_scores_alert_id", "alert_id"),
        Index("ix_risk_scores_incident_id", "incident_id"),
        Index("ix_risk_scores_total_score", "total_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联告警 ID",
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联事件 ID",
    )
    total_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="总风险评分（0-100）"
    )
    asset_importance_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="资产重要性评分"
    )
    asset_importance_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="资产重要性因素明细"
    )
    rpki_evidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="RPKI 证据评分"
    )
    rpki_evidence_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="RPKI 证据因素明细"
    )
    bgp_propagation_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="BGP 传播证据评分"
    )
    bgp_propagation_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="BGP 传播因素明细"
    )
    authorization_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="授权与变更证据评分"
    )
    authorization_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="授权与变更因素明细"
    )
    historical_baseline_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="历史与行为基线评分"
    )
    historical_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="历史因素明细"
    )
    external_risk_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="外部风险特征评分"
    )
    external_risk_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="外部风险因素明细"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="置信度（0-1）"
    )
    recommended_actions: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="建议动作列表"
    )

    # 关联
    alert: Mapped[Alert | None] = relationship(back_populates="risk_scores")

    def __repr__(self) -> str:
        return f"<RiskScore(id={self.id}, total={self.total_score}, confidence={self.confidence})>"


__all__ = [
    "Alert",
    "DetectionRule",
    "Incident",
    "RiskScore",
]
