"""创建 BGP 路由安全检测引擎数据表

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-03 00:00:00

创建以下数据表：
- detection_rules：检测规则
- incidents：事件
- alerts：告警
- risk_scores：风险评分

并添加相关索引与外键约束。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 BGP 路由安全检测引擎相关表。"""

    # ──────────────────────────────────────────────
    # 检测规则表
    # ──────────────────────────────────────────────
    op.create_table(
        "detection_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="规则名称"),
        sa.Column(
            "code",
            sa.String(100),
            nullable=False,
            comment="规则唯一编码，用于幂等初始化",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="规则描述"),
        sa.Column(
            "rule_type",
            sa.String(50),
            nullable=False,
            comment=(
                "规则类型：hijack/subprefix_hijack/moas/route_leak/"
                "path_anomaly/withdraw_flap/rpki_invalid"
            ),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="是否启用",
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="100",
            comment="优先级（数值越小优先级越高）",
        ),
        sa.Column(
            "conditions", sa.JSON(), nullable=True, comment="规则条件配置"
        ),
        sa.Column(
            "thresholds", sa.JSON(), nullable=True, comment="阈值配置"
        ),
        sa.Column(
            "whitelist",
            sa.JSON(),
            nullable=True,
            comment="白名单配置（前缀/ASN/观察点）",
        ),
        sa.Column(
            "scope",
            sa.JSON(),
            nullable=True,
            comment="生效范围（前缀列表、ASN 列表等）",
        ),
        sa.Column(
            "severity",
            sa.String(10),
            nullable=False,
            server_default="P3",
            comment="严重等级：P0/P1/P2/P3/P4",
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            nullable=True,
            comment="租户 ID，用于多租户数据隔离",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_detection_rules_code"),
    )
    op.create_index(
        "ix_detection_rules_rule_type", "detection_rules", ["rule_type"]
    )
    op.create_index(
        "ix_detection_rules_enabled", "detection_rules", ["enabled"]
    )
    op.create_index(
        "ix_detection_rules_priority", "detection_rules", ["priority"]
    )
    op.create_index(
        "ix_detection_rules_severity", "detection_rules", ["severity"]
    )
    op.create_index(
        "ix_detection_rules_tenant_id", "detection_rules", ["tenant_id"]
    )

    # ──────────────────────────────────────────────
    # 事件表（先于告警表创建，因告警表外键引用事件表）
    # ──────────────────────────────────────────────
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "title", sa.String(500), nullable=False, comment="事件标题"
        ),
        sa.Column(
            "description", sa.Text(), nullable=True, comment="事件描述"
        ),
        sa.Column(
            "severity",
            sa.String(10),
            nullable=False,
            server_default="P3",
            comment="严重等级：P0/P1/P2/P3/P4",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
            comment=(
                "事件状态：open/investigating/mitigating/resolved/closed"
            ),
        ),
        sa.Column(
            "alert_ids", sa.JSON(), nullable=True, comment="关联告警 ID 列表"
        ),
        sa.Column(
            "affected_prefixes",
            sa.JSON(),
            nullable=True,
            comment="受影响前缀列表",
        ),
        sa.Column(
            "affected_asns",
            sa.JSON(),
            nullable=True,
            comment="受影响 ASN 列表",
        ),
        sa.Column(
            "assigned_to",
            sa.Integer(),
            nullable=True,
            comment="分派给的用户 ID",
        ),
        sa.Column(
            "root_cause", sa.Text(), nullable=True, comment="根因分析"
        ),
        sa.Column(
            "resolution", sa.Text(), nullable=True, comment="处置结论"
        ),
        sa.Column(
            "evidence", sa.JSON(), nullable=True, comment="事件证据"
        ),
        sa.Column(
            "timeline", sa.JSON(), nullable=True, comment="事件时间线"
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="首次发现时间",
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近发现时间",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="解决时间",
        ),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="关闭时间",
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            nullable=True,
            comment="租户 ID",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_assigned_to", "incidents", ["assigned_to"])
    op.create_index("ix_incidents_tenant_id", "incidents", ["tenant_id"])

    # ──────────────────────────────────────────────
    # 告警表
    # ──────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "rule_id",
            sa.Integer(),
            nullable=True,
            comment="触发的规则 ID",
        ),
        sa.Column(
            "alert_type",
            sa.String(50),
            nullable=False,
            comment="告警类型，与规则 rule_type 对应",
        ),
        sa.Column(
            "severity",
            sa.String(10),
            nullable=False,
            server_default="P3",
            comment="严重等级：P0/P1/P2/P3/P4",
        ),
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=False,
            comment="关联的网络前缀",
        ),
        sa.Column(
            "origin_as",
            sa.Integer(),
            nullable=True,
            comment="关联的起源 AS 号",
        ),
        sa.Column(
            "as_path", sa.JSON(), nullable=True, comment="AS 路径列表"
        ),
        sa.Column(
            "observation_point_id",
            sa.Integer(),
            nullable=True,
            comment="观察点 ID",
        ),
        sa.Column(
            "title", sa.String(500), nullable=False, comment="告警标题"
        ),
        sa.Column(
            "description", sa.Text(), nullable=True, comment="告警描述"
        ),
        sa.Column(
            "evidence", sa.JSON(), nullable=True, comment="证据数据"
        ),
        sa.Column(
            "risk_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="风险评分（0-100）",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="置信度（0-1）",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="new",
            comment=(
                "处置状态：new/confirmed/assigned/resolved/closed/false_positive"
            ),
        ),
        sa.Column(
            "is_benign_conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否为良性冲突",
        ),
        sa.Column(
            "benign_conflict_type",
            sa.String(50),
            nullable=True,
            comment="良性冲突类型",
        ),
        sa.Column(
            "incident_id",
            sa.Integer(),
            nullable=True,
            comment="关联事件 ID",
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="首次发现时间",
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近发现时间",
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            nullable=True,
            comment="租户 ID",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["detection_rules.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["observation_point_id"],
            ["observation_points.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_rule_id", "alerts", ["rule_id"])
    op.create_index("ix_alerts_prefix", "alerts", ["prefix"])
    op.create_index("ix_alerts_origin_as", "alerts", ["origin_as"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_incident_id", "alerts", ["incident_id"])
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])

    # ──────────────────────────────────────────────
    # 风险评分表
    # ──────────────────────────────────────────────
    op.create_table(
        "risk_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "alert_id",
            sa.Integer(),
            nullable=True,
            comment="关联告警 ID",
        ),
        sa.Column(
            "incident_id",
            sa.Integer(),
            nullable=True,
            comment="关联事件 ID",
        ),
        sa.Column(
            "total_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="总风险评分（0-100）",
        ),
        sa.Column(
            "asset_importance_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="资产重要性评分",
        ),
        sa.Column(
            "asset_importance_factors",
            sa.JSON(),
            nullable=True,
            comment="资产重要性因素明细",
        ),
        sa.Column(
            "rpki_evidence_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="RPKI 证据评分",
        ),
        sa.Column(
            "rpki_evidence_factors",
            sa.JSON(),
            nullable=True,
            comment="RPKI 证据因素明细",
        ),
        sa.Column(
            "bgp_propagation_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="BGP 传播证据评分",
        ),
        sa.Column(
            "bgp_propagation_factors",
            sa.JSON(),
            nullable=True,
            comment="BGP 传播因素明细",
        ),
        sa.Column(
            "authorization_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="授权与变更证据评分",
        ),
        sa.Column(
            "authorization_factors",
            sa.JSON(),
            nullable=True,
            comment="授权与变更因素明细",
        ),
        sa.Column(
            "historical_baseline_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="历史与行为基线评分",
        ),
        sa.Column(
            "historical_factors",
            sa.JSON(),
            nullable=True,
            comment="历史因素明细",
        ),
        sa.Column(
            "external_risk_score",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="外部风险特征评分",
        ),
        sa.Column(
            "external_risk_factors",
            sa.JSON(),
            nullable=True,
            comment="外部风险因素明细",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="置信度（0-1）",
        ),
        sa.Column(
            "recommended_actions",
            sa.JSON(),
            nullable=True,
            comment="建议动作列表",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_scores_alert_id", "risk_scores", ["alert_id"])
    op.create_index(
        "ix_risk_scores_incident_id", "risk_scores", ["incident_id"]
    )
    op.create_index(
        "ix_risk_scores_total_score", "risk_scores", ["total_score"]
    )


def downgrade() -> None:
    """回滚：删除 BGP 路由安全检测引擎相关表。"""
    op.drop_index("ix_risk_scores_total_score", table_name="risk_scores")
    op.drop_index("ix_risk_scores_incident_id", table_name="risk_scores")
    op.drop_index("ix_risk_scores_alert_id", table_name="risk_scores")
    op.drop_table("risk_scores")

    op.drop_index("ix_alerts_tenant_id", table_name="alerts")
    op.drop_index("ix_alerts_incident_id", table_name="alerts")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_origin_as", table_name="alerts")
    op.drop_index("ix_alerts_prefix", table_name="alerts")
    op.drop_index("ix_alerts_rule_id", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_incidents_tenant_id", table_name="incidents")
    op.drop_index("ix_incidents_assigned_to", table_name="incidents")
    op.drop_index("ix_incidents_severity", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index("ix_detection_rules_tenant_id", table_name="detection_rules")
    op.drop_index("ix_detection_rules_severity", table_name="detection_rules")
    op.drop_index("ix_detection_rules_priority", table_name="detection_rules")
    op.drop_index("ix_detection_rules_enabled", table_name="detection_rules")
    op.drop_index("ix_detection_rules_rule_type", table_name="detection_rules")
    op.drop_table("detection_rules")
