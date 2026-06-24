"""创建资源资产管理数据表

Revision ID: 0003
Revises: 0002
Create Date: 2025-02-01 00:00:00

创建以下数据表：
- business_services：业务服务
- customers：客户
- routers：路由器
- prefixes：IP 前缀（含自引用父子关系与索引）
- asns：AS 自治系统
- bgp_peers：BGP 邻居

注意：prefixes.customer_id 与 bgp_peers.router_id 引用上述表，
故 business_services/customers/routers 必须先创建。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建资源资产管理相关表。"""

    # ──────────────────────────────────────────────
    # 业务服务表
    # ──────────────────────────────────────────────
    op.create_table(
        "business_services",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="业务服务名称"),
        sa.Column("description", sa.String(500), nullable=True, comment="业务描述"),
        sa.Column("importance", sa.String(20), nullable=False, comment="重要度"),
        sa.Column("owner_contact", sa.String(255), nullable=True, comment="业务负责人联系方式"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
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
    op.create_index("ix_business_services_name", "business_services", ["name"])
    op.create_index(
        "ix_business_services_importance", "business_services", ["importance"]
    )

    # ──────────────────────────────────────────────
    # 客户表
    # ──────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="客户名称"),
        sa.Column("contact_name", sa.String(255), nullable=True, comment="客户联系人姓名"),
        sa.Column("contact_email", sa.String(255), nullable=True, comment="客户联系人邮箱"),
        sa.Column("contract_id", sa.String(100), nullable=True, comment="合同编号"),
        sa.Column("service_level", sa.String(50), nullable=False, comment="服务等级"),
        sa.Column("status", sa.String(20), nullable=False, comment="状态"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
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
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_index("ix_customers_status", "customers", ["status"])

    # ──────────────────────────────────────────────
    # 路由器表
    # ──────────────────────────────────────────────
    op.create_table(
        "routers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False, comment="主机名"),
        sa.Column("vendor", sa.String(100), nullable=True, comment="厂商"),
        sa.Column("model", sa.String(100), nullable=True, comment="设备型号"),
        sa.Column("management_ip", sa.String(64), nullable=True, comment="管理 IP 地址"),
        sa.Column("location", sa.String(255), nullable=True, comment="部署位置"),
        sa.Column("snmp_community", sa.String(255), nullable=True, comment="SNMP community 字符串"),
        sa.Column("status", sa.String(20), nullable=False, comment="状态"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
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
    op.create_index("ix_routers_hostname", "routers", ["hostname"])
    op.create_index("ix_routers_status", "routers", ["status"])

    # ──────────────────────────────────────────────
    # IP 前缀表
    # ──────────────────────────────────────────────
    op.create_table(
        "prefixes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prefix", sa.String(64), nullable=False, comment="CIDR 表示的 IP 前缀"),
        sa.Column("prefix_family", sa.Integer(), nullable=False, comment="IP 协议族：4 或 6"),
        sa.Column("prefix_length", sa.Integer(), nullable=False, comment="前缀长度"),
        sa.Column("parent_id", sa.Integer(), nullable=True, comment="父前缀 ID"),
        sa.Column("status", sa.String(20), nullable=False, comment="状态"),
        sa.Column("importance", sa.String(20), nullable=False, comment="重要度"),
        sa.Column("business_service", sa.String(255), nullable=True, comment="业务归属"),
        sa.Column("region", sa.String(100), nullable=True, comment="地域"),
        sa.Column("site", sa.String(100), nullable=True, comment="机房"),
        sa.Column("cloud_zone", sa.String(100), nullable=True, comment="云区域"),
        sa.Column("customer_id", sa.Integer(), nullable=True, comment="关联客户 ID"),
        sa.Column("tags", sa.JSON(), nullable=True, comment="标签列表"),
        sa.Column("description", sa.String(500), nullable=True, comment="描述"),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True, comment="登记时间"),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True, comment="过期时间"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
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
        sa.ForeignKeyConstraint(["parent_id"], ["prefixes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prefix", name="uq_prefixes_prefix"),
    )
    op.create_index("ix_prefixes_prefix", "prefixes", ["prefix"])
    op.create_index(
        "ix_prefixes_family_length", "prefixes", ["prefix_family", "prefix_length"]
    )
    op.create_index("ix_prefixes_status", "prefixes", ["status"])
    op.create_index("ix_prefixes_parent_id", "prefixes", ["parent_id"])
    op.create_index("ix_prefixes_customer_id", "prefixes", ["customer_id"])

    # ──────────────────────────────────────────────
    # ASN 表
    # ──────────────────────────────────────────────
    op.create_table(
        "asns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asn", sa.Integer(), nullable=False, comment="AS 号码"),
        sa.Column("name", sa.String(255), nullable=False, comment="AS 名称"),
        sa.Column("asn_type", sa.String(50), nullable=False, comment="AS 关系类型"),
        sa.Column("status", sa.String(20), nullable=False, comment="状态"),
        sa.Column("risk_profile", sa.String(500), nullable=True, comment="风险画像描述"),
        sa.Column("contact_name", sa.String(255), nullable=True, comment="联系人姓名"),
        sa.Column("contact_email", sa.String(255), nullable=True, comment="联系人邮箱"),
        sa.Column("noc_phone", sa.String(50), nullable=True, comment="NOC 联系电话"),
        sa.Column("emergency_contact", sa.String(500), nullable=True, comment="紧急联系方式"),
        sa.Column("relationship_tags", sa.JSON(), nullable=True, comment="关系标签列表"),
        sa.Column("description", sa.String(500), nullable=True, comment="描述"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
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
        sa.UniqueConstraint("asn", name="uq_asns_asn"),
    )
    op.create_index("ix_asns_asn", "asns", ["asn"])
    op.create_index("ix_asns_asn_type", "asns", ["asn_type"])
    op.create_index("ix_asns_status", "asns", ["status"])

    # ──────────────────────────────────────────────
    # BGP 邻居表
    # ──────────────────────────────────────────────
    op.create_table(
        "bgp_peers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("peer_ip", sa.String(64), nullable=False, comment="邻居 IP 地址"),
        sa.Column("remote_asn", sa.Integer(), nullable=False, comment="远端 ASN"),
        sa.Column("address_family", sa.String(20), nullable=False, comment="地址族"),
        sa.Column("session_type", sa.String(20), nullable=False, comment="会话类型"),
        sa.Column("routing_policy", sa.String(500), nullable=True, comment="路由策略描述"),
        sa.Column("max_prefixes", sa.Integer(), nullable=True, comment="最大前缀数"),
        sa.Column("session_state", sa.String(20), nullable=False, comment="会话状态"),
        sa.Column("router_id", sa.Integer(), nullable=True, comment="关联路由器 ID"),
        sa.Column("description", sa.String(500), nullable=True, comment="描述"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
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
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "peer_ip", "remote_asn", name="uq_bgp_peers_peer_ip_remote_asn"
        ),
    )
    op.create_index("ix_bgp_peers_peer_ip", "bgp_peers", ["peer_ip"])
    op.create_index("ix_bgp_peers_remote_asn", "bgp_peers", ["remote_asn"])
    op.create_index("ix_bgp_peers_session_state", "bgp_peers", ["session_state"])
    op.create_index("ix_bgp_peers_router_id", "bgp_peers", ["router_id"])


def downgrade() -> None:
    """回滚：删除资源资产管理相关表。"""
    op.drop_index("ix_bgp_peers_router_id", table_name="bgp_peers")
    op.drop_index("ix_bgp_peers_session_state", table_name="bgp_peers")
    op.drop_index("ix_bgp_peers_remote_asn", table_name="bgp_peers")
    op.drop_index("ix_bgp_peers_peer_ip", table_name="bgp_peers")
    op.drop_table("bgp_peers")

    op.drop_index("ix_asns_status", table_name="asns")
    op.drop_index("ix_asns_asn_type", table_name="asns")
    op.drop_index("ix_asns_asn", table_name="asns")
    op.drop_table("asns")

    op.drop_index("ix_prefixes_customer_id", table_name="prefixes")
    op.drop_index("ix_prefixes_parent_id", table_name="prefixes")
    op.drop_index("ix_prefixes_status", table_name="prefixes")
    op.drop_index("ix_prefixes_family_length", table_name="prefixes")
    op.drop_index("ix_prefixes_prefix", table_name="prefixes")
    op.drop_table("prefixes")

    op.drop_index("ix_routers_status", table_name="routers")
    op.drop_index("ix_routers_hostname", table_name="routers")
    op.drop_table("routers")

    op.drop_index("ix_customers_status", table_name="customers")
    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_table("customers")

    op.drop_index("ix_business_services_importance", table_name="business_services")
    op.drop_index("ix_business_services_name", table_name="business_services")
    op.drop_table("business_services")
