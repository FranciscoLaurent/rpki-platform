"""初始迁移：创建数据库扩展。

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# 迁移版本号
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 citext 扩展（不区分大小写的文本类型）。

    SQLite 不支持 CREATE EXTENSION，跳过。
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")


def downgrade() -> None:
    """降级：移除 citext 扩展。"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP EXTENSION IF EXISTS citext")
