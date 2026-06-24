"""创建 RPKI-RTR 服务与设备集成相关数据表

Revision ID: 0009
Revises: 0008
Create Date: 2025-04-15 00:00:00

创建以下数据表：
- rtr_servers：RTR 服务实例
- rtr_sessions：RTR 客户端会话
- rtr_serial_history：RTR 序列号历史
- device_config_templates：设备配置模板

并添加相关索引与外键约束。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 RPKI-RTR 服务与设备集成相关表。"""

    # ──────────────────────────────────────────────
    # RTR 服务实例表
    # ──────────────────────────────────────────────
    op.create_table(
        "rtr_servers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "name", sa.String(255), nullable=False, comment="RTR 服务名称"
        ),
        sa.Column(
            "listen_host",
            sa.String(64),
            nullable=False,
            server_default="0.0.0.0",
            comment="监听地址",
        ),
        sa.Column(
            "listen_port",
            sa.Integer(),
            nullable=False,
            server_default="8282",
            comment="监听端口",
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="RTR Session ID，缓存重启后需变更",
        ),
        sa.Column(
            "current_serial",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前序列号，每次 VRP 更新递增",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="stopped",
            comment="服务状态：running/stopped/error",
        ),
        sa.Column(
            "vrps_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前 VRP 数量",
        ),
        sa.Column(
            "connected_clients",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前连接客户端数",
        ),
        sa.Column(
            "mtls_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否启用 mTLS 双向认证",
        ),
        sa.Column(
            "whitelist",
            sa.JSON(),
            nullable=True,
            comment="允许连接的客户端 IP 列表（空表示不限制）",
        ),
        sa.Column(
            "config",
            sa.JSON(),
            nullable=True,
            comment="其他配置（如刷新间隔、超时等）",
        ),
        sa.Column(
            "last_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次启动时间",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="最近一次错误信息",
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
        "ix_rtr_servers_status", "rtr_servers", ["status"]
    )
    op.create_index(
        "ix_rtr_servers_tenant_id", "rtr_servers", ["tenant_id"]
    )
    op.create_index(
        "ix_rtr_servers_listen_host_port",
        "rtr_servers",
        ["listen_host", "listen_port"],
    )

    # ──────────────────────────────────────────────
    # RTR 客户端会话表
    # ──────────────────────────────────────────────
    op.create_table(
        "rtr_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "server_id",
            sa.Integer(),
            nullable=False,
            comment="所属 RTR 服务 ID",
        ),
        sa.Column(
            "client_ip",
            sa.String(64),
            nullable=False,
            comment="客户端 IP 地址",
        ),
        sa.Column(
            "client_port",
            sa.Integer(),
            nullable=True,
            comment="客户端端口",
        ),
        sa.Column(
            "client_version",
            sa.Integer(),
            nullable=True,
            comment="RTR 协议版本：0 或 1",
        ),
        sa.Column(
            "session_state",
            sa.String(20),
            nullable=False,
            server_default="idle",
            comment="会话状态：established/syncing/idle/error",
        ),
        sa.Column(
            "last_serial",
            sa.Integer(),
            nullable=True,
            comment="客户端最后同步的序列号",
        ),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="连接建立时间",
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近活动时间",
        ),
        sa.Column(
            "bytes_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已发送字节数",
        ),
        sa.Column(
            "bytes_received",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已接收字节数",
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
            ["server_id"],
            ["rtr_servers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rtr_sessions_server_id", "rtr_sessions", ["server_id"]
    )
    op.create_index(
        "ix_rtr_sessions_client_ip", "rtr_sessions", ["client_ip"]
    )
    op.create_index(
        "ix_rtr_sessions_session_state",
        "rtr_sessions",
        ["session_state"],
    )

    # ──────────────────────────────────────────────
    # RTR 序列号历史表
    # ──────────────────────────────────────────────
    op.create_table(
        "rtr_serial_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "server_id",
            sa.Integer(),
            nullable=False,
            comment="所属 RTR 服务 ID",
        ),
        sa.Column(
            "serial_number",
            sa.Integer(),
            nullable=False,
            comment="序列号",
        ),
        sa.Column(
            "change_type",
            sa.String(30),
            nullable=False,
            comment=(
                "变更类型：full_update/incremental_update/rollback"
            ),
        ),
        sa.Column(
            "vrps_added",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="新增 VRP 数量",
        ),
        sa.Column(
            "vrps_removed",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="移除 VRP 数量",
        ),
        sa.Column(
            "vrps_modified",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="修改 VRP 数量",
        ),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            nullable=True,
            comment="关联的 RPKI 快照 ID",
        ),
        sa.Column(
            "note", sa.Text(), nullable=True, comment="备注"
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
            ["server_id"],
            ["rtr_servers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rtr_serial_history_server_id",
        "rtr_serial_history",
        ["server_id"],
    )
    op.create_index(
        "ix_rtr_serial_history_serial_number",
        "rtr_serial_history",
        ["serial_number"],
    )
    op.create_index(
        "ix_rtr_serial_history_change_type",
        "rtr_serial_history",
        ["change_type"],
    )
    op.create_index(
        "ix_rtr_serial_history_created_at",
        "rtr_serial_history",
        ["created_at"],
    )

    # ──────────────────────────────────────────────
    # 设备配置模板表
    # ──────────────────────────────────────────────
    op.create_table(
        "device_config_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "name", sa.String(255), nullable=False, comment="模板名称"
        ),
        sa.Column(
            "vendor",
            sa.String(50),
            nullable=False,
            comment=(
                "厂商：cisco_ios_xe/cisco_ios_xr/juniper_junos/huawei_vrp/"
                "h3c/arista_eos/nokia_sros/frr/bird/openbgpd"
            ),
        ),
        sa.Column(
            "template_type",
            sa.String(30),
            nullable=False,
            comment=(
                "模板类型：rtr_client/rov_policy/rollback/risk_notice"
            ),
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="模板内容，含变量占位符（如 {{ asn }}）",
        ),
        sa.Column(
            "variables",
            sa.JSON(),
            nullable=True,
            comment="变量定义（变量名、描述、是否必填、默认值等）",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="模板描述",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="是否启用",
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
        "ix_device_config_templates_vendor",
        "device_config_templates",
        ["vendor"],
    )
    op.create_index(
        "ix_device_config_templates_template_type",
        "device_config_templates",
        ["template_type"],
    )
    op.create_index(
        "ix_device_config_templates_enabled",
        "device_config_templates",
        ["enabled"],
    )
    op.create_index(
        "ix_device_config_templates_tenant_id",
        "device_config_templates",
        ["tenant_id"],
    )


def downgrade() -> None:
    """回滚：删除 RPKI-RTR 服务与设备集成相关表。"""
    op.drop_index(
        "ix_device_config_templates_tenant_id",
        table_name="device_config_templates",
    )
    op.drop_index(
        "ix_device_config_templates_enabled",
        table_name="device_config_templates",
    )
    op.drop_index(
        "ix_device_config_templates_template_type",
        table_name="device_config_templates",
    )
    op.drop_index(
        "ix_device_config_templates_vendor",
        table_name="device_config_templates",
    )
    op.drop_table("device_config_templates")

    op.drop_index(
        "ix_rtr_serial_history_created_at",
        table_name="rtr_serial_history",
    )
    op.drop_index(
        "ix_rtr_serial_history_change_type",
        table_name="rtr_serial_history",
    )
    op.drop_index(
        "ix_rtr_serial_history_serial_number",
        table_name="rtr_serial_history",
    )
    op.drop_index(
        "ix_rtr_serial_history_server_id",
        table_name="rtr_serial_history",
    )
    op.drop_table("rtr_serial_history")

    op.drop_index(
        "ix_rtr_sessions_session_state", table_name="rtr_sessions"
    )
    op.drop_index(
        "ix_rtr_sessions_client_ip", table_name="rtr_sessions"
    )
    op.drop_index(
        "ix_rtr_sessions_server_id", table_name="rtr_sessions"
    )
    op.drop_table("rtr_sessions")

    op.drop_index(
        "ix_rtr_servers_listen_host_port", table_name="rtr_servers"
    )
    op.drop_index(
        "ix_rtr_servers_tenant_id", table_name="rtr_servers"
    )
    op.drop_index("ix_rtr_servers_status", table_name="rtr_servers")
    op.drop_table("rtr_servers")
