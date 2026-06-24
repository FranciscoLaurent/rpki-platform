"""创建 API Key 数据表

Revision ID: 0010
Revises: 0009
Create Date: 2025-04-16 00:00:00

创建以下数据表：
- api_keys：API 密钥

并添加相关索引与外键约束。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="密钥名称"),
        sa.Column(
            "key_hash",
            sa.String(255),
            nullable=False,
            comment="密钥哈希值（bcrypt）",
        ),
        sa.Column(
            "key_prefix",
            sa.String(32),
            nullable=False,
            comment="密钥前缀（用于展示与识别）",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="所属用户 ID",
        ),
        sa.Column(
            "scopes",
            sa.JSON(),
            nullable=True,
            comment="权限范围列表",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否启用",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="过期时间",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后使用时间",
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
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="API 密钥表",
    )
    op.create_index(
        "ix_api_keys_user_id", "api_keys", ["user_id"]
    )
    op.create_index(
        "ix_api_keys_tenant_id", "api_keys", ["tenant_id"]
    )
    op.create_index(
        "ix_api_keys_key_prefix", "api_keys", ["key_prefix"]
    )
    op.create_index(
        "ix_api_keys_is_active", "api_keys", ["is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_is_active", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")
