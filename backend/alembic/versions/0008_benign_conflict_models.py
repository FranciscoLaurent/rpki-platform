"""创建 ROA 良性冲突相关数据表

Revision ID: 0008
Revises: 0007
Create Date: 2025-01-04 00:00:00

创建以下数据表：
- benign_conflict_records：良性冲突记录
- maintenance_windows：维护窗口
- scrubber_authorizations：清洗商授权
- anycast_nodes：Anycast 节点登记

并添加相关索引与外键约束。

注意：
    本迁移显式建表，不依赖 ``app.models.__init__`` 自动注册
    （共享文件不可修改）。模型类在 ``app.models.benign_conflict`` 中定义，
    使用方需显式导入。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 ROA 良性冲突相关表。"""

    # ──────────────────────────────────────────────
    # 良性冲突记录表
    # ──────────────────────────────────────────────
    op.create_table(
        "benign_conflict_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "alert_id",
            sa.Integer(),
            nullable=True,
            comment="关联告警 ID",
        ),
        sa.Column(
            "conflict_type",
            sa.String(50),
            nullable=False,
            comment=(
                "冲突类型：ddos_scrubbing/anycast_expansion/planned_maintenance/"
                "resource_transfer/data_source_delay/customer_misconfig"
            ),
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
            comment="观测到的起源 AS 号",
        ),
        sa.Column(
            "expected_origin_as",
            sa.Integer(),
            nullable=True,
            comment="期望的起源 AS 号（资产台账/ROA 授权）",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
            comment="置信度（0-1）",
        ),
        sa.Column(
            "evidence", sa.JSON(), nullable=True, comment="证据数据"
        ),
        sa.Column(
            "recommendation",
            sa.Text(),
            nullable=True,
            comment="处理建议",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="suspected",
            comment="状态：suspected/confirmed/dismissed",
        ),
        sa.Column(
            "valid_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="授权时间窗结束时间",
        ),
        sa.Column(
            "related_work_order",
            sa.String(100),
            nullable=True,
            comment="关联工单号",
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
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_benign_conflict_records_alert_id",
        "benign_conflict_records",
        ["alert_id"],
    )
    op.create_index(
        "ix_benign_conflict_records_conflict_type",
        "benign_conflict_records",
        ["conflict_type"],
    )
    op.create_index(
        "ix_benign_conflict_records_prefix",
        "benign_conflict_records",
        ["prefix"],
    )
    op.create_index(
        "ix_benign_conflict_records_origin_as",
        "benign_conflict_records",
        ["origin_as"],
    )
    op.create_index(
        "ix_benign_conflict_records_status",
        "benign_conflict_records",
        ["status"],
    )
    op.create_index(
        "ix_benign_conflict_records_tenant_id",
        "benign_conflict_records",
        ["tenant_id"],
    )

    # ──────────────────────────────────────────────
    # 维护窗口表
    # ──────────────────────────────────────────────
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            comment="维护窗口名称",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="维护描述",
        ),
        sa.Column(
            "start_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="开始时间",
        ),
        sa.Column(
            "end_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="结束时间",
        ),
        sa.Column(
            "prefixes",
            sa.JSON(),
            nullable=True,
            comment="受影响前缀列表",
        ),
        sa.Column(
            "asns",
            sa.JSON(),
            nullable=True,
            comment="受影响 ASN 列表",
        ),
        sa.Column(
            "approved_by",
            sa.Integer(),
            nullable=True,
            comment="审批人用户 ID",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="scheduled",
            comment="状态：scheduled/active/completed/cancelled",
        ),
        sa.Column(
            "work_order_id",
            sa.String(100),
            nullable=True,
            comment="关联工单号",
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
    op.create_index(
        "ix_maintenance_windows_status",
        "maintenance_windows",
        ["status"],
    )
    op.create_index(
        "ix_maintenance_windows_start_time",
        "maintenance_windows",
        ["start_time"],
    )
    op.create_index(
        "ix_maintenance_windows_end_time",
        "maintenance_windows",
        ["end_time"],
    )
    op.create_index(
        "ix_maintenance_windows_work_order_id",
        "maintenance_windows",
        ["work_order_id"],
    )
    op.create_index(
        "ix_maintenance_windows_tenant_id",
        "maintenance_windows",
        ["tenant_id"],
    )

    # ──────────────────────────────────────────────
    # 清洗商授权表
    # ──────────────────────────────────────────────
    op.create_table(
        "scrubber_authorizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "scrubber_asn",
            sa.Integer(),
            nullable=False,
            comment="清洗商 AS 号",
        ),
        sa.Column(
            "customer_prefix",
            sa.String(64),
            nullable=False,
            comment="客户前缀（CIDR）",
        ),
        sa.Column(
            "customer_asn",
            sa.Integer(),
            nullable=False,
            comment="客户 AS 号",
        ),
        sa.Column(
            "authorized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="授权时间",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="授权截止时间",
        ),
        sa.Column(
            "work_order_id",
            sa.String(100),
            nullable=True,
            comment="关联工单号",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="状态：active/expired/revoked",
        ),
        sa.Column(
            "contact_info",
            sa.JSON(),
            nullable=True,
            comment="联系人信息",
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
    op.create_index(
        "ix_scrubber_authorizations_scrubber_asn",
        "scrubber_authorizations",
        ["scrubber_asn"],
    )
    op.create_index(
        "ix_scrubber_authorizations_customer_prefix",
        "scrubber_authorizations",
        ["customer_prefix"],
    )
    op.create_index(
        "ix_scrubber_authorizations_customer_asn",
        "scrubber_authorizations",
        ["customer_asn"],
    )
    op.create_index(
        "ix_scrubber_authorizations_status",
        "scrubber_authorizations",
        ["status"],
    )
    op.create_index(
        "ix_scrubber_authorizations_expires_at",
        "scrubber_authorizations",
        ["expires_at"],
    )
    op.create_index(
        "ix_scrubber_authorizations_tenant_id",
        "scrubber_authorizations",
        ["tenant_id"],
    )

    # ──────────────────────────────────────────────
    # Anycast 节点登记表
    # ──────────────────────────────────────────────
    op.create_table(
        "anycast_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "node_asn",
            sa.Integer(),
            nullable=False,
            comment="Anycast 节点 AS 号",
        ),
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=False,
            comment="Anycast 前缀（CIDR）",
        ),
        sa.Column(
            "region",
            sa.String(100),
            nullable=True,
            comment="地域",
        ),
        sa.Column(
            "site",
            sa.String(100),
            nullable=True,
            comment="机房",
        ),
        sa.Column(
            "business_tag",
            sa.String(100),
            nullable=True,
            comment="业务标签",
        ),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="登记时间",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="状态：active/inactive",
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
    op.create_index(
        "ix_anycast_nodes_node_asn",
        "anycast_nodes",
        ["node_asn"],
    )
    op.create_index(
        "ix_anycast_nodes_prefix",
        "anycast_nodes",
        ["prefix"],
    )
    op.create_index(
        "ix_anycast_nodes_status",
        "anycast_nodes",
        ["status"],
    )
    op.create_index(
        "ix_anycast_nodes_region",
        "anycast_nodes",
        ["region"],
    )
    op.create_index(
        "ix_anycast_nodes_tenant_id",
        "anycast_nodes",
        ["tenant_id"],
    )


def downgrade() -> None:
    """回滚：删除 ROA 良性冲突相关表。"""

    # Anycast 节点表
    op.drop_index("ix_anycast_nodes_tenant_id", table_name="anycast_nodes")
    op.drop_index("ix_anycast_nodes_region", table_name="anycast_nodes")
    op.drop_index("ix_anycast_nodes_status", table_name="anycast_nodes")
    op.drop_index("ix_anycast_nodes_prefix", table_name="anycast_nodes")
    op.drop_index("ix_anycast_nodes_node_asn", table_name="anycast_nodes")
    op.drop_table("anycast_nodes")

    # 清洗商授权表
    op.drop_index(
        "ix_scrubber_authorizations_tenant_id",
        table_name="scrubber_authorizations",
    )
    op.drop_index(
        "ix_scrubber_authorizations_expires_at",
        table_name="scrubber_authorizations",
    )
    op.drop_index(
        "ix_scrubber_authorizations_status",
        table_name="scrubber_authorizations",
    )
    op.drop_index(
        "ix_scrubber_authorizations_customer_asn",
        table_name="scrubber_authorizations",
    )
    op.drop_index(
        "ix_scrubber_authorizations_customer_prefix",
        table_name="scrubber_authorizations",
    )
    op.drop_index(
        "ix_scrubber_authorizations_scrubber_asn",
        table_name="scrubber_authorizations",
    )
    op.drop_table("scrubber_authorizations")

    # 维护窗口表
    op.drop_index(
        "ix_maintenance_windows_tenant_id",
        table_name="maintenance_windows",
    )
    op.drop_index(
        "ix_maintenance_windows_work_order_id",
        table_name="maintenance_windows",
    )
    op.drop_index(
        "ix_maintenance_windows_end_time",
        table_name="maintenance_windows",
    )
    op.drop_index(
        "ix_maintenance_windows_start_time",
        table_name="maintenance_windows",
    )
    op.drop_index(
        "ix_maintenance_windows_status",
        table_name="maintenance_windows",
    )
    op.drop_table("maintenance_windows")

    # 良性冲突记录表
    op.drop_index(
        "ix_benign_conflict_records_tenant_id",
        table_name="benign_conflict_records",
    )
    op.drop_index(
        "ix_benign_conflict_records_status",
        table_name="benign_conflict_records",
    )
    op.drop_index(
        "ix_benign_conflict_records_origin_as",
        table_name="benign_conflict_records",
    )
    op.drop_index(
        "ix_benign_conflict_records_prefix",
        table_name="benign_conflict_records",
    )
    op.drop_index(
        "ix_benign_conflict_records_conflict_type",
        table_name="benign_conflict_records",
    )
    op.drop_index(
        "ix_benign_conflict_records_alert_id",
        table_name="benign_conflict_records",
    )
    op.drop_table("benign_conflict_records")
