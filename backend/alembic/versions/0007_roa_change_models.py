"""创建 ROA 变更审批相关数据表

Revision ID: 0007
Revises: 0006
Create Date: 2025-06-21 00:00:00

创建以下数据表：
- roa_change_requests：ROA 变更请求
- roa_approval_rules：ROA 审批规则

并添加相关索引与外键约束，支撑 ROA 高级管理能力（P1）：
审批控制与变更后验证。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 ROA 变更审批相关表。"""

    # ──────────────────────────────────────────────
    # 审批规则表（先于变更请求表创建，因变更请求表外键引用审批规则表）
    # ──────────────────────────────────────────────
    op.create_table(
        "roa_approval_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "name", sa.String(255), nullable=False, comment="规则名称"
        ),
        sa.Column(
            "description", sa.Text(), nullable=True, comment="规则描述"
        ),
        sa.Column(
            "rule_type",
            sa.String(20),
            nullable=False,
            comment=(
                "审批类型：auto_approve/single_approval/"
                "dual_approval/committee"
            ),
        ),
        sa.Column(
            "conditions",
            sa.JSON(),
            nullable=True,
            comment=(
                "触发条件（JSON），如 "
                '{"change_type": ["revoke"], "prefix_importance": ["critical"], '
                '"risk_level": ["high", "critical"]}'
            ),
        ),
        sa.Column(
            "approvers",
            sa.JSON(),
            nullable=True,
            comment="审批人 ID 列表",
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
    )
    op.create_index(
        "ix_roa_approval_rules_rule_type",
        "roa_approval_rules",
        ["rule_type"],
    )
    op.create_index(
        "ix_roa_approval_rules_enabled",
        "roa_approval_rules",
        ["enabled"],
    )
    op.create_index(
        "ix_roa_approval_rules_priority",
        "roa_approval_rules",
        ["priority"],
    )
    op.create_index(
        "ix_roa_approval_rules_tenant_id",
        "roa_approval_rules",
        ["tenant_id"],
    )

    # ──────────────────────────────────────────────
    # 变更请求表
    # ──────────────────────────────────────────────
    op.create_table(
        "roa_change_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "change_type",
            sa.String(20),
            nullable=False,
            comment="变更类型：create/modify/revoke",
        ),
        sa.Column(
            "roa_id",
            sa.Integer(),
            nullable=True,
            comment="关联的 ROA ID（修改/撤销时填写）",
        ),
        # 变更后的值
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=True,
            comment="变更后的前缀",
        ),
        sa.Column(
            "origin_as",
            sa.Integer(),
            nullable=True,
            comment="变更后的起源 AS 号",
        ),
        sa.Column(
            "max_length",
            sa.Integer(),
            nullable=True,
            comment="变更后的最大前缀长度",
        ),
        # 变更前的值（用于回滚）
        sa.Column(
            "current_prefix",
            sa.String(64),
            nullable=True,
            comment="变更前的前缀",
        ),
        sa.Column(
            "current_origin_as",
            sa.Integer(),
            nullable=True,
            comment="变更前的起源 AS 号",
        ),
        sa.Column(
            "current_max_length",
            sa.Integer(),
            nullable=True,
            comment="变更前的最大前缀长度",
        ),
        # 变更原因与影响评估
        sa.Column(
            "reason", sa.Text(), nullable=False, comment="变更原因"
        ),
        sa.Column(
            "impact_summary",
            sa.JSON(),
            nullable=True,
            comment="影响评估摘要（JSON）",
        ),
        sa.Column(
            "risk_level",
            sa.String(20),
            nullable=False,
            server_default="low",
            comment="风险等级：low/medium/high/critical",
        ),
        # 审批状态与流程
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending_approval",
            comment=(
                "状态：draft/pending_approval/approved/rejected/"
                "executed/failed/rolled_back"
            ),
        ),
        sa.Column(
            "approval_rule_id",
            sa.Integer(),
            nullable=True,
            comment="匹配的审批规则 ID",
        ),
        sa.Column(
            "required_approvals",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="所需审批人数（由审批规则决定）",
        ),
        sa.Column(
            "approvals",
            sa.JSON(),
            nullable=True,
            comment="审批记录列表（含审批人、动作、意见、时间）",
        ),
        # 申请人与审批人
        sa.Column(
            "requested_by",
            sa.Integer(),
            nullable=False,
            comment="申请人 ID",
        ),
        sa.Column(
            "approved_by",
            sa.Integer(),
            nullable=True,
            comment="最终审批人 ID",
        ),
        sa.Column(
            "approval_comments",
            sa.Text(),
            nullable=True,
            comment="审批意见",
        ),
        # 执行信息
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="执行时间",
        ),
        sa.Column(
            "execution_result",
            sa.JSON(),
            nullable=True,
            comment="执行结果（JSON）",
        ),
        # 回滚信息
        sa.Column(
            "rollback_info",
            sa.JSON(),
            nullable=True,
            comment="回滚信息（JSON）",
        ),
        # 多租户与时间戳
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
        sa.ForeignKeyConstraint(
            ["roa_id"], ["roas.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approval_rule_id"],
            ["roa_approval_rules.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_roa_change_requests_change_type",
        "roa_change_requests",
        ["change_type"],
    )
    op.create_index(
        "ix_roa_change_requests_roa_id",
        "roa_change_requests",
        ["roa_id"],
    )
    op.create_index(
        "ix_roa_change_requests_status",
        "roa_change_requests",
        ["status"],
    )
    op.create_index(
        "ix_roa_change_requests_risk_level",
        "roa_change_requests",
        ["risk_level"],
    )
    op.create_index(
        "ix_roa_change_requests_requested_by",
        "roa_change_requests",
        ["requested_by"],
    )
    op.create_index(
        "ix_roa_change_requests_approved_by",
        "roa_change_requests",
        ["approved_by"],
    )
    op.create_index(
        "ix_roa_change_requests_tenant_id",
        "roa_change_requests",
        ["tenant_id"],
    )


def downgrade() -> None:
    """回滚：删除 ROA 变更审批相关表。"""
    op.drop_index(
        "ix_roa_change_requests_tenant_id",
        table_name="roa_change_requests",
    )
    op.drop_index(
        "ix_roa_change_requests_approved_by",
        table_name="roa_change_requests",
    )
    op.drop_index(
        "ix_roa_change_requests_requested_by",
        table_name="roa_change_requests",
    )
    op.drop_index(
        "ix_roa_change_requests_risk_level",
        table_name="roa_change_requests",
    )
    op.drop_index(
        "ix_roa_change_requests_status",
        table_name="roa_change_requests",
    )
    op.drop_index(
        "ix_roa_change_requests_roa_id",
        table_name="roa_change_requests",
    )
    op.drop_index(
        "ix_roa_change_requests_change_type",
        table_name="roa_change_requests",
    )
    op.drop_table("roa_change_requests")

    op.drop_index(
        "ix_roa_approval_rules_tenant_id",
        table_name="roa_approval_rules",
    )
    op.drop_index(
        "ix_roa_approval_rules_priority",
        table_name="roa_approval_rules",
    )
    op.drop_index(
        "ix_roa_approval_rules_enabled",
        table_name="roa_approval_rules",
    )
    op.drop_index(
        "ix_roa_approval_rules_rule_type",
        table_name="roa_approval_rules",
    )
    op.drop_table("roa_approval_rules")
