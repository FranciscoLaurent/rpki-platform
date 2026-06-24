"""RPKI 数据模型：TAL、仓库、对象、ROA、VRP、快照与缓存。

包含 RPKI 仓库同步与对象验证所需的全部数据表模型。
所有模型继承自 ``app.models.base.Base``，业务表混入 ``TimestampMixin``。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TAL(Base, TimestampMixin):
    """Trust Anchor Locator（信任锚定位符）模型。

    表示一个 RPKI 信任锚，包含 RRDP 与 rsync 两种获取方式的 URI。
    """

    __tablename__ = "tals"
    __table_args__ = (
        Index("ix_tals_status", "status"),
        Index("ix_tals_sync_status", "sync_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="TAL 名称"
    )
    uri: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="RRDP URI"
    )
    rsync_uri: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="rsync URI"
    )
    raw_tal: Mapped[str] = mapped_column(
        Text, nullable=False, comment="原始 TAL 文件内容"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="TAL 状态：active/disabled",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后同步时间"
    )
    sync_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="同步状态：success/failed/running/pending",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次同步错误信息"
    )

    # 关联仓库
    repositories: Mapped[list[RPKIRepository]] = relationship(
        back_populates="tal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TAL(id={self.id}, name={self.name})>"


class RPKIRepository(Base, TimestampMixin):
    """RPKI 仓库模型，表示一个 RRDP 或 rsync 同步源。"""

    __tablename__ = "rpki_repositories"
    __table_args__ = (
        Index("ix_rpki_repositories_tal_id", "tal_id"),
        Index("ix_rpki_repositories_status", "status"),
        Index("ix_rpki_repositories_sync_status", "sync_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tal_id: Mapped[int] = mapped_column(
        ForeignKey("tals.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 TAL ID",
    )
    uri: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="仓库 URI"
    )
    protocol: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="同步协议：rrdp/rsync"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="仓库状态：active/disabled",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后同步时间"
    )
    sync_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="同步状态：success/failed/running/pending",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次同步错误信息"
    )
    object_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="仓库内对象数量"
    )

    # 关联
    tal: Mapped[TAL] = relationship(back_populates="repositories")
    objects: Mapped[list[RPKIObject]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RPKIRepository(id={self.id}, uri={self.uri})>"


class RPKIObject(Base, TimestampMixin):
    """RPKI 对象模型，存储从仓库同步的原始对象及其解析结果。"""

    __tablename__ = "rpki_objects"
    __table_args__ = (
        Index("ix_rpki_objects_repository_id", "repository_id"),
        Index("ix_rpki_objects_object_type", "object_type"),
        Index("ix_rpki_objects_status", "status"),
        Index("ix_rpki_objects_uri", "uri"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("rpki_repositories.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属仓库 ID",
    )
    object_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="对象类型：certificate/roa/manifest/crl/ghostbusters",
    )
    uri: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="对象 URI"
    )
    serial_number: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="证书序列号"
    )
    signing_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="签名时间"
    )
    not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="有效期起始"
    )
    not_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="有效期截止"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="valid",
        comment="对象状态：valid/expired/revoked",
    )
    raw_data: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, comment="原始对象数据（DER 编码）"
    )
    parsed_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="解析后的对象数据（JSON）"
    )

    # 关联
    repository: Mapped[RPKIRepository] = relationship(back_populates="objects")
    roas: Mapped[list[ROA]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RPKIObject(id={self.id}, type={self.object_type}, uri={self.uri})>"


class ROA(Base, TimestampMixin):
    """ROA（Route Origin Authorization）模型，从 RPKI 对象解析得到。"""

    __tablename__ = "roas"
    __table_args__ = (
        Index("ix_roas_prefix_origin_as", "prefix", "origin_as"),
        Index("ix_roas_origin_as", "origin_as"),
        Index("ix_roas_tal_id", "tal_id"),
        Index("ix_roas_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_id: Mapped[int] = mapped_column(
        ForeignKey("rpki_objects.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的 RPKI 对象 ID",
    )
    prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="网络前缀（含前缀长度）"
    )
    prefix_family: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀族：4/6"
    )
    prefix_length: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀长度"
    )
    origin_as: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="授权的起源 AS 号"
    )
    max_length: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="最大前缀长度"
    )
    tal_id: Mapped[int | None] = mapped_column(
        ForeignKey("tals.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属 TAL ID",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="valid",
        comment="ROA 状态：valid/expired/revoked",
    )
    not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="有效期起始"
    )
    not_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="有效期截止"
    )

    # 关联
    object: Mapped[RPKIObject] = relationship(back_populates="roas")
    vrps: Mapped[list[VRP]] = relationship(
        back_populates="roa", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ROA(id={self.id}, prefix={self.prefix}, origin_as={self.origin_as})>"


class VRP(Base, TimestampMixin):
    """VRP（Validated ROA Payload）模型，用于 BGP 公告验证。"""

    __tablename__ = "vrps"
    __table_args__ = (
        Index("ix_vrps_prefix_origin_as", "prefix", "origin_as"),
        Index("ix_vrps_origin_as", "origin_as"),
        Index("ix_vrps_tal_id", "tal_id"),
        Index("ix_vrps_prefix", "prefix"),
        Index("ix_vrps_validation_status", "validation_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="网络前缀（含前缀长度）"
    )
    prefix_family: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀族：4/6"
    )
    prefix_length: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀长度"
    )
    origin_as: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="授权的起源 AS 号"
    )
    max_length: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="最大前缀长度"
    )
    tal_id: Mapped[int | None] = mapped_column(
        ForeignKey("tals.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属 TAL ID",
    )
    roa_id: Mapped[int | None] = mapped_column(
        ForeignKey("roas.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的 ROA ID",
    )
    trust_anchor: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="信任锚名称"
    )
    validation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="valid",
        comment="验证状态：valid/invalid/not_found",
    )

    # 关联
    roa: Mapped[ROA | None] = relationship(back_populates="vrps")

    def __repr__(self) -> str:
        return (
            f"<VRP(id={self.id}, prefix={self.prefix}, "
            f"origin_as={self.origin_as})>"
        )


class RPKISnapshot(Base, TimestampMixin):
    """RPKI 快照模型，记录某一时刻的 VRP/ROA/对象数量与元数据。"""

    __tablename__ = "rpki_snapshots"
    __table_args__ = (
        Index("ix_rpki_snapshots_snapshot_time", "snapshot_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="快照时间",
    )
    vrp_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="VRP 数量"
    )
    roa_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="ROA 数量"
    )
    object_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="RPKI 对象数量"
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="快照元数据（VRP/ROA 列表摘要等）",
    )

    def __repr__(self) -> str:
        return f"<RPKISnapshot(id={self.id}, time={self.snapshot_time})>"


class RPKICache(Base, TimestampMixin):
    """RPKI 缓存状态模型，记录 VRP 缓存的版本与统计信息。"""

    __tablename__ = "rpki_caches"
    __table_args__ = (
        Index("ix_rpki_caches_name", "name"),
        Index("ix_rpki_caches_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="缓存名称"
    )
    version: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="缓存版本"
    )
    vrp_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="VRP 数量"
    )
    last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后更新时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unknown",
        comment="缓存状态：healthy/stale/unknown",
    )

    def __repr__(self) -> str:
        return f"<RPKICache(id={self.id}, name={self.name})>"
