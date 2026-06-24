"""BGP 数据采集层数据模型。

包含 BGP 数据源、观察点、BGP 公告、BGP 撤路、RIB 快照与设备适配器模型。
PostgreSQL 仅存储热数据用于关联查询，大量历史数据存储在 ClickHouse。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    pass


class BGPDataSource(Base, TimestampMixin, TenantMixin):
    """BGP 数据源模型。

    描述一个 BGP 数据采集来源，可以是公开数据源（RIPE RIS、RouteViews）、
    路由服务器、商业数据源、BMP 接入或内部采集。
    """

    __tablename__ = "bgp_data_sources"
    __table_args__ = (
        Index("ix_bgp_data_sources_status", "status"),
        Index("ix_bgp_data_sources_source_type", "source_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="数据源名称"
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="数据源类型：ripe_ris/routeviews/route_server/commercial/bmp/internal",
    )
    protocol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="采集协议：bgp_live_stream/mrt_rib/bmp/snmp/netconf/restconf/gnmi/cli",
    )
    endpoint: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="数据源端点（URL 或连接地址）"
    )
    credentials: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="加密存储的凭据"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="disabled",
        comment="数据源状态：active/disabled/error",
    )
    trust_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        comment="数据源可信度：high/medium/low",
    )
    coverage: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="覆盖范围描述"
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后连接时间"
    )
    last_error: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="最后错误信息"
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="数据源特定配置"
    )

    # 关联观察点
    observation_points: Mapped[list["ObservationPoint"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BGPDataSource(id={self.id}, name={self.name}, type={self.source_type})>"


class ObservationPoint(Base, TimestampMixin):
    """观察点模型。

    描述一个 BGP 观察点，通常对应一个采集器（如 RIS 的 RRC、RouteViews 的采集器）。
    """

    __tablename__ = "observation_points"
    __table_args__ = (
        Index("ix_observation_points_data_source_id", "data_source_id"),
        Index("ix_observation_points_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="观察点名称"
    )
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey("bgp_data_sources.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属数据源 ID",
    )
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="观察点地理位置"
    )
    collector_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="采集器标识，如 RIS 的 RRC 编号"
    )
    ip_version: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="dual",
        comment="IP 版本：4/6/dual",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="观察点状态：active/disabled",
    )

    # 关联数据源
    data_source: Mapped["BGPDataSource"] = relationship(
        back_populates="observation_points"
    )

    def __repr__(self) -> str:
        return f"<ObservationPoint(id={self.id}, name={self.name})>"


class BGPAnnouncement(Base, TenantMixin):
    """BGP 公告模型（热数据）。

    存储 BGP 路由公告，用于关联查询与实时分析。
    大量历史数据存储在 ClickHouse，PostgreSQL 仅保留热数据。
    """

    __tablename__ = "bgp_announcements"
    __table_args__ = (
        Index("ix_bgp_announcements_prefix", "prefix"),
        Index("ix_bgp_announcements_origin_as", "origin_as"),
        Index("ix_bgp_announcements_timestamp", "timestamp"),
        Index("ix_bgp_announcements_observation_point_id", "observation_point_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="网络前缀，如 192.168.1.0/24"
    )
    prefix_family: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀地址族：4 或 6"
    )
    prefix_length: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀长度"
    )
    origin_as: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="起源 AS 号"
    )
    as_path: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="AS 路径列表"
    )
    next_hop: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="下一跳地址"
    )
    communities: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="BGP Community 列表"
    )
    large_communities: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="BGP Large Community 列表"
    )
    med: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="MULTI_EXIT_DISC 值"
    )
    local_pref: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="LOCAL_PREF 值"
    )
    observation_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("observation_points.id", ondelete="SET NULL"),
        nullable=True,
        comment="观察点 ID",
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("bgp_data_sources.id", ondelete="SET NULL"),
        nullable=True,
        comment="数据源 ID",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="公告观测时间",
    )
    address_family: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4,
        comment="地址族：4 (IPv4) 或 6 (IPv6)",
    )
    rpki_validation_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="RPKI 验证状态：valid/invalid/not_found",
    )
    rpki_invalid_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="RPKI 验证失败原因"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间",
    )

    def __repr__(self) -> str:
        return f"<BGPAnnouncement(id={self.id}, prefix={self.prefix}, origin_as={self.origin_as})>"


class BGPWithdraw(Base, TenantMixin):
    """BGP 撤路模型。

    存储 BGP 路由撤销事件。
    """

    __tablename__ = "bgp_withdraws"
    __table_args__ = (
        Index("ix_bgp_withdraws_prefix", "prefix"),
        Index("ix_bgp_withdraws_timestamp", "timestamp"),
        Index("ix_bgp_withdraws_observation_point_id", "observation_point_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="被撤销的网络前缀"
    )
    prefix_family: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀地址族：4 或 6"
    )
    prefix_length: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀长度"
    )
    observation_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("observation_points.id", ondelete="SET NULL"),
        nullable=True,
        comment="观察点 ID",
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("bgp_data_sources.id", ondelete="SET NULL"),
        nullable=True,
        comment="数据源 ID",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="撤路观测时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间",
    )

    def __repr__(self) -> str:
        return f"<BGPWithdraw(id={self.id}, prefix={self.prefix})>"


class BGPRibSnapshot(Base, TimestampMixin):
    """BGP RIB 快照模型。

    记录 RIB 快照的元信息，实际路由数据存储在 ClickHouse 或文件存储。
    """

    __tablename__ = "bgp_rib_snapshots"
    __table_args__ = (
        Index("ix_bgp_rib_snapshots_observation_point_id", "observation_point_id"),
        Index("ix_bgp_rib_snapshots_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("observation_points.id", ondelete="SET NULL"),
        nullable=True,
        comment="观察点 ID",
    )
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="快照时间",
    )
    route_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="路由条目数",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        comment="快照状态：running/completed/failed",
    )

    def __repr__(self) -> str:
        return f"<BGPRibSnapshot(id={self.id}, status={self.status})>"


class DeviceAdapter(Base, TimestampMixin, TenantMixin):
    """设备适配器配置模型。

    描述一个网络设备的适配器配置，用于通过 SNMP/NETCONF/RESTCONF/gNMI/CLI/BMP
    等协议采集 BGP 数据。
    """

    __tablename__ = "device_adapters"
    __table_args__ = (
        Index("ix_device_adapters_vendor", "vendor"),
        Index("ix_device_adapters_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="适配器名称"
    )
    vendor: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="设备厂商：cisco/juniper/huawei/h3c/arista/nokia/frr/bird/openbgpd",
    )
    model: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="设备型号"
    )
    connection_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="连接类型：snmp/netconf/restconf/gnmi/cli/bmp",
    )
    endpoint: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="设备端点（IP 或主机名）"
    )
    credentials: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="加密存储的凭据"
    )
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="设备能力描述"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="disabled",
        comment="适配器状态：active/disabled/error",
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后连接时间"
    )
    last_error: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="最后错误信息"
    )

    def __repr__(self) -> str:
        return f"<DeviceAdapter(id={self.id}, name={self.name}, vendor={self.vendor})>"
