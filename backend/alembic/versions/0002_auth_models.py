"""创建认证与权限系统数据表

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00

创建以下数据表：
- tenants / tenant_members：租户与成员
- users / roles / permissions / role_permissions / user_roles：用户与 RBAC
- audit_logs：审计日志

并插入系统内置角色与权限。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0002"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建表并插入初始数据。"""

    # ──────────────────────────────────────────────
    # 租户表
    # ──────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="租户名称"),
        sa.Column("slug", sa.String(100), nullable=False, comment="租户短标识"),
        sa.Column("status", sa.String(20), nullable=False, comment="租户状态"),
        sa.Column("settings", sa.JSON(), nullable=False, comment="租户配置"),
        sa.Column("max_users", sa.Integer(), nullable=False, comment="最大用户数"),
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
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # ──────────────────────────────────────────────
    # 用户表
    # ──────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False, comment="邮箱地址"),
        sa.Column("username", sa.String(100), nullable=False, comment="用户名"),
        sa.Column("full_name", sa.String(255), nullable=True, comment="姓名"),
        sa.Column("hashed_password", sa.String(255), nullable=False, comment="密码哈希"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, comment="是否超级管理员"),
        sa.Column("status", sa.String(20), nullable=False, comment="用户状态"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True, comment="最后登录时间"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, comment="连续登录失败次数"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True, comment="锁定截止时间"),
        sa.Column("mfa_secret", sa.String(255), nullable=True, comment="MFA 密钥"),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, comment="是否需要强制修改密码"),
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
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # ──────────────────────────────────────────────
    # 角色表
    # ──────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, comment="角色名称"),
        sa.Column("code", sa.String(100), nullable=False, comment="角色编码"),
        sa.Column("description", sa.String(500), nullable=True, comment="角色描述"),
        sa.Column("is_system", sa.Boolean(), nullable=False, comment="是否系统内置角色"),
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
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_index("ix_roles_code", "roles", ["code"])

    # ──────────────────────────────────────────────
    # 权限表
    # ──────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, comment="权限名称"),
        sa.Column("code", sa.String(100), nullable=False, comment="权限编码"),
        sa.Column("resource", sa.String(100), nullable=False, comment="资源类型"),
        sa.Column("action", sa.String(50), nullable=False, comment="动作类型"),
        sa.Column("description", sa.String(500), nullable=True, comment="权限描述"),
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
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])

    # ──────────────────────────────────────────────
    # 角色-权限关联表
    # ──────────────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # ──────────────────────────────────────────────
    # 用户-角色关联表
    # ──────────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    # ──────────────────────────────────────────────
    # 租户成员表
    # ──────────────────────────────────────────────
    op.create_table(
        "tenant_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, comment="租户内角色"),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_tenant_member"),
    )
    op.create_index("ix_tenant_members_user_id", "tenant_members", ["user_id"])
    op.create_index("ix_tenant_members_tenant_id", "tenant_members", ["tenant_id"])

    # ──────────────────────────────────────────────
    # 审计日志表
    # ──────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True, comment="操作用户 ID"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="租户 ID"),
        sa.Column("action", sa.String(100), nullable=False, comment="操作动作"),
        sa.Column("resource_type", sa.String(100), nullable=True, comment="资源类型"),
        sa.Column("resource_id", sa.String(100), nullable=True, comment="资源 ID"),
        sa.Column("details", sa.JSON(), nullable=True, comment="操作详情"),
        sa.Column("ip_address", sa.String(45), nullable=True, comment="IP 地址"),
        sa.Column("user_agent", sa.String(500), nullable=True, comment="User-Agent"),
        sa.Column("request_id", sa.String(100), nullable=True, comment="请求追踪 ID"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="记录创建时间",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ──────────────────────────────────────────────
    # 插入系统内置权限
    # ──────────────────────────────────────────────
    permissions_data = [
        {"name": "查看用户", "code": "user:read", "resource": "user", "action": "read", "description": "查看用户信息"},
        {"name": "创建/编辑用户", "code": "user:write", "resource": "user", "action": "write", "description": "创建或编辑用户"},
        {"name": "删除用户", "code": "user:delete", "resource": "user", "action": "delete", "description": "删除用户"},
        {"name": "查看角色", "code": "role:read", "resource": "role", "action": "read", "description": "查看角色信息"},
        {"name": "创建/编辑角色", "code": "role:write", "resource": "role", "action": "write", "description": "创建或编辑角色"},
        {"name": "删除角色", "code": "role:delete", "resource": "role", "action": "delete", "description": "删除角色"},
        {"name": "查看权限", "code": "permission:read", "resource": "permission", "action": "read", "description": "查看权限列表"},
        {"name": "查看租户", "code": "tenant:read", "resource": "tenant", "action": "read", "description": "查看租户信息"},
        {"name": "创建/编辑租户", "code": "tenant:write", "resource": "tenant", "action": "write", "description": "创建或编辑租户"},
        {"name": "删除租户", "code": "tenant:delete", "resource": "tenant", "action": "delete", "description": "删除租户"},
        {"name": "查看审计日志", "code": "audit:read", "resource": "audit", "action": "read", "description": "查看审计日志"},
        {"name": "查看前缀", "code": "prefix:read", "resource": "prefix", "action": "read", "description": "查看前缀信息"},
        {"name": "创建/编辑前缀", "code": "prefix:write", "resource": "prefix", "action": "write", "description": "创建或编辑前缀"},
        {"name": "删除前缀", "code": "prefix:delete", "resource": "prefix", "action": "delete", "description": "删除前缀"},
        {"name": "查看 ROA", "code": "roa:read", "resource": "roa", "action": "read", "description": "查看 ROA 信息"},
        {"name": "创建/编辑 ROA", "code": "roa:write", "resource": "roa", "action": "write", "description": "创建或编辑 ROA"},
        {"name": "审批 ROA", "code": "roa:approve", "resource": "roa", "action": "approve", "description": "审批 ROA 请求"},
        {"name": "删除 ROA", "code": "roa:delete", "resource": "roa", "action": "delete", "description": "删除 ROA"},
        {"name": "查看 BGP 监测", "code": "bgp:read", "resource": "bgp", "action": "read", "description": "查看 BGP 监测数据"},
        {"name": "编辑 BGP 监测", "code": "bgp:write", "resource": "bgp", "action": "write", "description": "编辑 BGP 监测配置"},
        {"name": "系统管理", "code": "system:admin", "resource": "system", "action": "admin", "description": "系统管理权限"},
    ]
    permissions_table = sa.table(
        "permissions",
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("resource", sa.String),
        sa.column("action", sa.String),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(permissions_table, permissions_data)

    # ──────────────────────────────────────────────
    # 插入系统内置角色
    # ──────────────────────────────────────────────
    roles_data = [
        {"name": "超级管理员", "code": "super_admin", "description": "拥有系统全部权限", "is_system": True},
        {"name": "网络管理员", "code": "network_admin", "description": "管理网络前缀与 ROA", "is_system": True},
        {"name": "RPKI 管理员", "code": "rpki_admin", "description": "管理 RPKI 相关资源", "is_system": True},
        {"name": "NOC 操作员", "code": "noc_operator", "description": "网络运营中心操作员", "is_system": True},
        {"name": "安全分析师", "code": "security_analyst", "description": "安全审计与分析", "is_system": True},
        {"name": "审批人", "code": "approver", "description": "审批 ROA 请求", "is_system": True},
        {"name": "客户", "code": "customer", "description": "租户客户", "is_system": True},
        {"name": "API 服务", "code": "api_service", "description": "API 集成服务账号", "is_system": True},
    ]
    roles_table = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(roles_table, roles_data)


def downgrade() -> None:
    """回滚：删除所有表。"""
    op.drop_table("audit_logs")
    op.drop_table("tenant_members")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_roles_code", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
