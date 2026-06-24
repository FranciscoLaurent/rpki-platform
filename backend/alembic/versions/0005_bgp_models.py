"""创建 BGP 数据采集层数据表

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-02 00:00:00

创建以下数据表：
- bgp_data_sources：BGP 数据源
- observation_points：观察点
- bgp_announcements：BGP 公告（热数据）
- bgp_withdraws：BGP 撤路
- bgp_rib_snapshots：RIB 快照
- device_adapters：设备适配器

并添加相关索引。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 BGP 数据采集层相关表。"""

    # ──────────────────────────────────────────────
    # BGP 数据源表
    # ──────────────────────────────────────────────
    op.create_table(
        "bgp_data_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="数据源名称"),
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=False,
            comment="数据源类型：ripe_ris/routeviews/route_server/commercial/bmp/internal",
        ),
        sa.Column(
            "protocol",
            sa.String(50),
            nullable=False,
            comment="采集协议：bgp_live_stream/mrt_rib/bmp/snmp/netconf/restconf/gnmi/cli",
        ),
        sa.Column(
            "endpoint",
            sa.String(500),
            nullable=False,
            comment="数据源端点（URL 或连接地址）",
        ),
        sa.Column("credentials", sa.JSON(), nullable=True, comment="加密存储的凭据"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="disabled",
            comment="数据源状态：active/disabled/error",
        ),
        sa.Column(
            "trust_level",
            sa.String(20),
            nullable=False,
            server_default="medium",
            comment="数据源可信度：high/medium/low",
        ),
        sa.Column("coverage", sa.JSON(), nullable=True, comment="覆盖范围描述"),
        sa.Column(
            "last_connected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后连接时间",
        ),
        sa.Column(
            "last_error",
            sa.String(1000),
            nullable=True,
            comment="最后错误信息",
        ),
        sa.Column("config", sa.JSON(), nullable=True, comment="数据源特定配置"),
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
    op.create_index("ix_bgp_data_sources_status", "bgp_data_sources", ["status"])
    op.create_index(
        "ix_bgp_data_sources_source_type", "bgp_data_sources", ["source_type"]
    )
    op.create_index(
        "ix_bgp_data_sources_tenant_id", "bgp_data_sources", ["tenant_id"]
    )

    # ──────────────────────────────────────────────
    # 观察点表
    # ──────────────────────────────────────────────
    op.create_table(
        "observation_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="观察点名称"),
        sa.Column(
            "data_source_id",
            sa.Integer(),
            nullable=False,
            comment="所属数据源 ID",
        ),
        sa.Column(
            "location",
            sa.String(255),
            nullable=True,
            comment="观察点地理位置",
        ),
        sa.Column(
            "collector_id",
            sa.String(100),
            nullable=True,
            comment="采集器标识，如 RIS 的 RRC 编号",
        ),
        sa.Column(
            "ip_version",
            sa.String(10),
            nullable=False,
            server_default="dual",
            comment="IP 版本：4/6/dual",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="观察点状态：active/disabled",
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
            ["data_source_id"],
            ["bgp_data_sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_observation_points_data_source_id",
        "observation_points",
        ["data_source_id"],
    )
    op.create_index("ix_observation_points_status", "observation_points", ["status"])

    # ──────────────────────────────────────────────
    # BGP 公告表（热数据）
    # ──────────────────────────────────────────────
    op.create_table(
        "bgp_announcements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=False,
            comment="网络前缀，如 192.168.1.0/24",
        ),
        sa.Column(
            "prefix_family",
            sa.Integer(),
            nullable=False,
            comment="前缀地址族：4 或 6",
        ),
        sa.Column(
            "prefix_length",
            sa.Integer(),
            nullable=False,
            comment="前缀长度",
        ),
        sa.Column("origin_as", sa.Integer(), nullable=True, comment="起源 AS 号"),
        sa.Column("as_path", sa.JSON(), nullable=True, comment="AS 路径列表"),
        sa.Column(
            "next_hop",
            sa.String(64),
            nullable=True,
            comment="下一跳地址",
        ),
        sa.Column(
            "communities",
            sa.JSON(),
            nullable=True,
            comment="BGP Community 列表",
        ),
        sa.Column(
            "large_communities",
            sa.JSON(),
            nullable=True,
            comment="BGP Large Community 列表",
        ),
        sa.Column(
            "med",
            sa.Integer(),
            nullable=True,
            comment="MULTI_EXIT_DISC 值",
        ),
        sa.Column(
            "local_pref",
            sa.Integer(),
            nullable=True,
            comment="LOCAL_PREF 值",
        ),
        sa.Column(
            "observation_point_id",
            sa.Integer(),
            nullable=True,
            comment="观察点 ID",
        ),
        sa.Column(
            "data_source_id",
            sa.Integer(),
            nullable=True,
            comment="数据源 ID",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="公告观测时间",
        ),
        sa.Column(
            "address_family",
            sa.Integer(),
            nullable=False,
            server_default="4",
            comment="地址族：4 (IPv4) 或 6 (IPv6)",
        ),
        sa.Column(
            "rpki_validation_status",
            sa.String(20),
            nullable=True,
            comment="RPKI 验证状态：valid/invalid/not_found",
        ),
        sa.Column(
            "rpki_invalid_reason",
            sa.String(255),
            nullable=True,
            comment="RPKI 验证失败原因",
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
            comment="记录创建时间",
        ),
        sa.ForeignKeyConstraint(
            ["observation_point_id"],
            ["observation_points.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["bgp_data_sources.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bgp_announcements_prefix", "bgp_announcements", ["prefix"])
    op.create_index(
        "ix_bgp_announcements_origin_as", "bgp_announcements", ["origin_as"]
    )
    op.create_index(
        "ix_bgp_announcements_timestamp", "bgp_announcements", ["timestamp"]
    )
    op.create_index(
        "ix_bgp_announcements_observation_point_id",
        "bgp_announcements",
        ["observation_point_id"],
    )
    op.create_index(
        "ix_bgp_announcements_tenant_id", "bgp_announcements", ["tenant_id"]
    )

    # ──────────────────────────────────────────────
    # BGP 撤路表
    # ──────────────────────────────────────────────
    op.create_table(
        "bgp_withdraws",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=False,
            comment="被撤销的网络前缀",
        ),
        sa.Column(
            "prefix_family",
            sa.Integer(),
            nullable=False,
            comment="前缀地址族：4 或 6",
        ),
        sa.Column(
            "prefix_length",
            sa.Integer(),
            nullable=False,
            comment="前缀长度",
        ),
        sa.Column(
            "observation_point_id",
            sa.Integer(),
            nullable=True,
            comment="观察点 ID",
        ),
        sa.Column(
            "data_source_id",
            sa.Integer(),
            nullable=True,
            comment="数据源 ID",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="撤路观测时间",
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
            comment="记录创建时间",
        ),
        sa.ForeignKeyConstraint(
            ["observation_point_id"],
            ["observation_points.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["bgp_data_sources.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bgp_withdraws_prefix", "bgp_withdraws", ["prefix"])
    op.create_index("ix_bgp_withdraws_timestamp", "bgp_withdraws", ["timestamp"])
    op.create_index(
        "ix_bgp_withdraws_observation_point_id",
        "bgp_withdraws",
        ["observation_point_id"],
    )
    op.create_index("ix_bgp_withdraws_tenant_id", "bgp_withdraws", ["tenant_id"])

    # ──────────────────────────────────────────────
    # BGP RIB 快照表
    # ──────────────────────────────────────────────
    op.create_table(
        "bgp_rib_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "observation_point_id",
            sa.Integer(),
            nullable=True,
            comment="观察点 ID",
        ),
        sa.Column(
            "snapshot_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="快照时间",
        ),
        sa.Column(
            "route_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="路由条目数",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="running",
            comment="快照状态：running/completed/failed",
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
            ["observation_point_id"],
            ["observation_points.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bgp_rib_snapshots_observation_point_id",
        "bgp_rib_snapshots",
        ["observation_point_id"],
    )
    op.create_index("ix_bgp_rib_snapshots_status", "bgp_rib_snapshots", ["status"])

    # ──────────────────────────────────────────────
    # 设备适配器表
    # ──────────────────────────────────────────────
    op.create_table(
        "device_adapters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="适配器名称"),
        sa.Column(
            "vendor",
            sa.String(50),
            nullable=False,
            comment="设备厂商：cisco/juniper/huawei/h3c/arista/nokia/frr/bird/openbgpd",
        ),
        sa.Column(
            "model",
            sa.String(255),
            nullable=True,
            comment="设备型号",
        ),
        sa.Column(
            "connection_type",
            sa.String(50),
            nullable=False,
            comment="连接类型：snmp/netconf/restconf/gnmi/cli/bmp",
        ),
        sa.Column(
            "endpoint",
            sa.String(500),
            nullable=False,
            comment="设备端点（IP 或主机名）",
        ),
        sa.Column("credentials", sa.JSON(), nullable=True, comment="加密存储的凭据"),
        sa.Column(
            "capabilities",
            sa.JSON(),
            nullable=True,
            comment="设备能力描述",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="disabled",
            comment="适配器状态：active/disabled/error",
        ),
        sa.Column(
            "last_connected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后连接时间",
        ),
        sa.Column(
            "last_error",
            sa.String(1000),
            nullable=True,
            comment="最后错误信息",
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
    op.create_index("ix_device_adapters_vendor", "device_adapters", ["vendor"])
    op.create_index("ix_device_adapters_status", "device_adapters", ["status"])
    op.create_index("ix_device_adapters_tenant_id", "device_adapters", ["tenant_id"])


def downgrade() -> None:
    """回滚：删除 BGP 数据采集层相关表。"""
    op.drop_index("ix_device_adapters_tenant_id", table_name="device_adapters")
    op.drop_index("ix_device_adapters_status", table_name="device_adapters")
    op.drop_index("ix_device_adapters_vendor", table_name="device_adapters")
    op.drop_table("device_adapters")

    op.drop_index("ix_bgp_rib_snapshots_status", table_name="bgp_rib_snapshots")
    op.drop_index(
        "ix_bgp_rib_snapshots_observation_point_id", table_name="bgp_rib_snapshots"
    )
    op.drop_table("bgp_rib_snapshots")

    op.drop_index("ix_bgp_withdraws_tenant_id", table_name="bgp_withdraws")
    op.drop_index(
        "ix_bgp_withdraws_observation_point_id", table_name="bgp_withdraws"
    )
    op.drop_index("ix_bgp_withdraws_timestamp", table_name="bgp_withdraws")
    op.drop_index("ix_bgp_withdraws_prefix", table_name="bgp_withdraws")
    op.drop_table("bgp_withdraws")

    op.drop_index("ix_bgp_announcements_tenant_id", table_name="bgp_announcements")
    op.drop_index(
        "ix_bgp_announcements_observation_point_id", table_name="bgp_announcements"
    )
    op.drop_index("ix_bgp_announcements_timestamp", table_name="bgp_announcements")
    op.drop_index("ix_bgp_announcements_origin_as", table_name="bgp_announcements")
    op.drop_index("ix_bgp_announcements_prefix", table_name="bgp_announcements")
    op.drop_table("bgp_announcements")

    op.drop_index("ix_observation_points_status", table_name="observation_points")
    op.drop_index(
        "ix_observation_points_data_source_id", table_name="observation_points"
    )
    op.drop_table("observation_points")

    op.drop_index("ix_bgp_data_sources_tenant_id", table_name="bgp_data_sources")
    op.drop_index(
        "ix_bgp_data_sources_source_type", table_name="bgp_data_sources"
    )
    op.drop_index("ix_bgp_data_sources_status", table_name="bgp_data_sources")
    op.drop_table("bgp_data_sources")
