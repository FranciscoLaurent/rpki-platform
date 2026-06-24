"""创建 RPKI 仓库同步与对象验证相关数据表

Revision ID: 0004
Revises: 0003
Create Date: 2025-03-01 00:00:00

创建以下数据表：
- tals：Trust Anchor Locator（信任锚定位符）
- rpki_repositories：RPKI 仓库（RRDP/rsync 同步源）
- rpki_objects：RPKI 对象（证书/ROA/Manifest/CRL/Ghostbusters）
- roas：ROA（Route Origin Authorization）
- vrps：VRP（Validated ROA Payload）
- rpki_snapshots：RPKI 数据快照
- rpki_caches：RPKI 缓存状态

并添加必要的索引以支持高性能 VRP 查询与 BGP 公告验证。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 迁移版本号
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 RPKI 相关数据表。"""

    # ──────────────────────────────────────────────
    # TAL 表（Trust Anchor Locator）
    # ──────────────────────────────────────────────
    op.create_table(
        "tals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="TAL 名称"),
        sa.Column("uri", sa.String(1024), nullable=False, comment="RRDP URI"),
        sa.Column("rsync_uri", sa.String(1024), nullable=False, comment="rsync URI"),
        sa.Column("raw_tal", sa.Text(), nullable=False, comment="原始 TAL 文件内容"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="TAL 状态：active/disabled",
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后同步时间",
        ),
        sa.Column(
            "sync_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="同步状态：success/failed/running/pending",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="最近一次同步错误信息",
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
    op.create_index("ix_tals_status", "tals", ["status"])
    op.create_index("ix_tals_sync_status", "tals", ["sync_status"])

    # ──────────────────────────────────────────────
    # RPKI 仓库表
    # ──────────────────────────────────────────────
    op.create_table(
        "rpki_repositories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tal_id", sa.Integer(), nullable=False, comment="所属 TAL ID"),
        sa.Column("uri", sa.String(1024), nullable=False, comment="仓库 URI"),
        sa.Column(
            "protocol",
            sa.String(20),
            nullable=False,
            comment="同步协议：rrdp/rsync",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="仓库状态：active/disabled",
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后同步时间",
        ),
        sa.Column(
            "sync_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="同步状态：success/failed/running/pending",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="最近一次同步错误信息",
        ),
        sa.Column(
            "object_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="仓库内对象数量",
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
        sa.ForeignKeyConstraint(["tal_id"], ["tals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rpki_repositories_tal_id", "rpki_repositories", ["tal_id"])
    op.create_index(
        "ix_rpki_repositories_status", "rpki_repositories", ["status"]
    )
    op.create_index(
        "ix_rpki_repositories_sync_status", "rpki_repositories", ["sync_status"]
    )

    # ──────────────────────────────────────────────
    # RPKI 对象表
    # ──────────────────────────────────────────────
    op.create_table(
        "rpki_objects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "repository_id",
            sa.Integer(),
            nullable=False,
            comment="所属仓库 ID",
        ),
        sa.Column(
            "object_type",
            sa.String(50),
            nullable=False,
            comment="对象类型：certificate/roa/manifest/crl/ghostbusters",
        ),
        sa.Column("uri", sa.String(1024), nullable=False, comment="对象 URI"),
        sa.Column(
            "serial_number",
            sa.String(255),
            nullable=True,
            comment="证书序列号",
        ),
        sa.Column(
            "signing_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="签名时间",
        ),
        sa.Column(
            "not_before",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="有效期起始",
        ),
        sa.Column(
            "not_after",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="有效期截止",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="valid",
            comment="对象状态：valid/expired/revoked",
        ),
        sa.Column(
            "raw_data",
            sa.LargeBinary(),
            nullable=True,
            comment="原始对象数据（DER 编码）",
        ),
        sa.Column(
            "parsed_data",
            sa.JSON(),
            nullable=True,
            comment="解析后的对象数据（JSON）",
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
            ["repository_id"], ["rpki_repositories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rpki_objects_repository_id", "rpki_objects", ["repository_id"]
    )
    op.create_index(
        "ix_rpki_objects_object_type", "rpki_objects", ["object_type"]
    )
    op.create_index("ix_rpki_objects_status", "rpki_objects", ["status"])
    op.create_index("ix_rpki_objects_uri", "rpki_objects", ["uri"])

    # ──────────────────────────────────────────────
    # ROA 表
    # ──────────────────────────────────────────────
    op.create_table(
        "roas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "object_id",
            sa.Integer(),
            nullable=False,
            comment="关联的 RPKI 对象 ID",
        ),
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=False,
            comment="网络前缀（含前缀长度）",
        ),
        sa.Column(
            "prefix_family",
            sa.Integer(),
            nullable=False,
            comment="前缀族：4/6",
        ),
        sa.Column(
            "prefix_length",
            sa.Integer(),
            nullable=False,
            comment="前缀长度",
        ),
        sa.Column(
            "origin_as",
            sa.Integer(),
            nullable=False,
            comment="授权的起源 AS 号",
        ),
        sa.Column(
            "max_length",
            sa.Integer(),
            nullable=True,
            comment="最大前缀长度",
        ),
        sa.Column(
            "tal_id",
            sa.Integer(),
            nullable=True,
            comment="所属 TAL ID",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="valid",
            comment="ROA 状态：valid/expired/revoked",
        ),
        sa.Column(
            "not_before",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="有效期起始",
        ),
        sa.Column(
            "not_after",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="有效期截止",
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
            ["object_id"], ["rpki_objects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tal_id"], ["tals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_roas_prefix_origin_as", "roas", ["prefix", "origin_as"]
    )
    op.create_index("ix_roas_origin_as", "roas", ["origin_as"])
    op.create_index("ix_roas_tal_id", "roas", ["tal_id"])
    op.create_index("ix_roas_status", "roas", ["status"])

    # ──────────────────────────────────────────────
    # VRP 表
    # ──────────────────────────────────────────────
    op.create_table(
        "vrps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "prefix",
            sa.String(64),
            nullable=False,
            comment="网络前缀（含前缀长度）",
        ),
        sa.Column(
            "prefix_family",
            sa.Integer(),
            nullable=False,
            comment="前缀族：4/6",
        ),
        sa.Column(
            "prefix_length",
            sa.Integer(),
            nullable=False,
            comment="前缀长度",
        ),
        sa.Column(
            "origin_as",
            sa.Integer(),
            nullable=False,
            comment="授权的起源 AS 号",
        ),
        sa.Column(
            "max_length",
            sa.Integer(),
            nullable=True,
            comment="最大前缀长度",
        ),
        sa.Column(
            "tal_id",
            sa.Integer(),
            nullable=True,
            comment="所属 TAL ID",
        ),
        sa.Column(
            "roa_id",
            sa.Integer(),
            nullable=True,
            comment="关联的 ROA ID",
        ),
        sa.Column(
            "trust_anchor",
            sa.String(255),
            nullable=True,
            comment="信任锚名称",
        ),
        sa.Column(
            "validation_status",
            sa.String(20),
            nullable=False,
            server_default="valid",
            comment="验证状态：valid/invalid/not_found",
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
        sa.ForeignKeyConstraint(["tal_id"], ["tals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["roa_id"], ["roas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vrps_prefix_origin_as", "vrps", ["prefix", "origin_as"]
    )
    op.create_index("ix_vrps_origin_as", "vrps", ["origin_as"])
    op.create_index("ix_vrps_tal_id", "vrps", ["tal_id"])
    op.create_index("ix_vrps_prefix", "vrps", ["prefix"])
    op.create_index(
        "ix_vrps_validation_status", "vrps", ["validation_status"]
    )

    # ──────────────────────────────────────────────
    # RPKI 快照表
    # ──────────────────────────────────────────────
    op.create_table(
        "rpki_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "snapshot_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="快照时间",
        ),
        sa.Column(
            "vrp_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="VRP 数量",
        ),
        sa.Column(
            "roa_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="ROA 数量",
        ),
        sa.Column(
            "object_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="RPKI 对象数量",
        ),
        # 注意：metadata 是 SQLAlchemy 保留字，列名使用 metadata
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="快照元数据（VRP/ROA 列表摘要等）",
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
        "ix_rpki_snapshots_snapshot_time", "rpki_snapshots", ["snapshot_time"]
    )

    # ──────────────────────────────────────────────
    # RPKI 缓存状态表
    # ──────────────────────────────────────────────
    op.create_table(
        "rpki_caches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            comment="缓存名称",
        ),
        sa.Column(
            "version",
            sa.String(100),
            nullable=True,
            comment="缓存版本",
        ),
        sa.Column(
            "vrp_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="VRP 数量",
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后更新时间",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="unknown",
            comment="缓存状态：healthy/stale/unknown",
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
    op.create_index("ix_rpki_caches_name", "rpki_caches", ["name"])
    op.create_index("ix_rpki_caches_status", "rpki_caches", ["status"])


def downgrade() -> None:
    """回滚：删除 RPKI 相关数据表。"""
    op.drop_index("ix_rpki_caches_status", table_name="rpki_caches")
    op.drop_index("ix_rpki_caches_name", table_name="rpki_caches")
    op.drop_table("rpki_caches")

    op.drop_index(
        "ix_rpki_snapshots_snapshot_time", table_name="rpki_snapshots"
    )
    op.drop_table("rpki_snapshots")

    op.drop_index("ix_vrps_validation_status", table_name="vrps")
    op.drop_index("ix_vrps_prefix", table_name="vrps")
    op.drop_index("ix_vrps_tal_id", table_name="vrps")
    op.drop_index("ix_vrps_origin_as", table_name="vrps")
    op.drop_index("ix_vrps_prefix_origin_as", table_name="vrps")
    op.drop_table("vrps")

    op.drop_index("ix_roas_status", table_name="roas")
    op.drop_index("ix_roas_tal_id", table_name="roas")
    op.drop_index("ix_roas_origin_as", table_name="roas")
    op.drop_index("ix_roas_prefix_origin_as", table_name="roas")
    op.drop_table("roas")

    op.drop_index("ix_rpki_objects_uri", table_name="rpki_objects")
    op.drop_index("ix_rpki_objects_status", table_name="rpki_objects")
    op.drop_index("ix_rpki_objects_object_type", table_name="rpki_objects")
    op.drop_index("ix_rpki_objects_repository_id", table_name="rpki_objects")
    op.drop_table("rpki_objects")

    op.drop_index(
        "ix_rpki_repositories_sync_status", table_name="rpki_repositories"
    )
    op.drop_index("ix_rpki_repositories_status", table_name="rpki_repositories")
    op.drop_index("ix_rpki_repositories_tal_id", table_name="rpki_repositories")
    op.drop_table("rpki_repositories")

    op.drop_index("ix_tals_sync_status", table_name="tals")
    op.drop_index("ix_tals_status", table_name="tals")
    op.drop_table("tals")
