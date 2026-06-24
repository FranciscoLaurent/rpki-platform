"""BGP 相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ──────────────────────────────────────────────
# BGP 数据源
# ──────────────────────────────────────────────


class BGPDataSourceBase(BaseModel):
    """BGP 数据源基础模式。"""

    name: str = Field(..., max_length=255, description="数据源名称")
    source_type: str = Field(
        ...,
        description="数据源类型：ripe_ris/routeviews/route_server/commercial/bmp/internal",
    )
    protocol: str = Field(
        ...,
        description="采集协议：bgp_live_stream/mrt_rib/bmp/snmp/netconf/restconf/gnmi/cli",
    )
    endpoint: str = Field(..., max_length=500, description="数据源端点")
    credentials: dict[str, Any] | None = Field(None, description="加密存储的凭据")
    trust_level: str = Field(default="medium", description="数据源可信度：high/medium/low")
    coverage: dict[str, Any] | None = Field(None, description="覆盖范围描述")
    config: dict[str, Any] | None = Field(None, description="数据源特定配置")

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        """校验数据源类型。"""
        allowed = {
            "ripe_ris",
            "routeviews",
            "route_server",
            "commercial",
            "bmp",
            "internal",
        }
        if v not in allowed:
            raise ValueError(f"数据源类型必须是 {allowed} 之一")
        return v

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """校验采集协议。"""
        allowed = {
            "bgp_live_stream",
            "mrt_rib",
            "bmp",
            "snmp",
            "netconf",
            "restconf",
            "gnmi",
            "cli",
        }
        if v not in allowed:
            raise ValueError(f"采集协议必须是 {allowed} 之一")
        return v

    @field_validator("trust_level")
    @classmethod
    def validate_trust_level(cls, v: str) -> str:
        """校验可信度等级。"""
        allowed = {"high", "medium", "low"}
        if v not in allowed:
            raise ValueError(f"可信度必须是 {allowed} 之一")
        return v


class BGPDataSourceCreate(BGPDataSourceBase):
    """创建 BGP 数据源请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class BGPDataSourceUpdate(BaseModel):
    """更新 BGP 数据源请求。"""

    name: str | None = Field(None, max_length=255, description="数据源名称")
    endpoint: str | None = Field(None, max_length=500, description="数据源端点")
    credentials: dict[str, Any] | None = Field(None, description="加密存储的凭据")
    trust_level: str | None = Field(None, description="数据源可信度")
    coverage: dict[str, Any] | None = Field(None, description="覆盖范围描述")
    config: dict[str, Any] | None = Field(None, description="数据源特定配置")
    status: str | None = Field(None, description="数据源状态")

    @field_validator("trust_level")
    @classmethod
    def validate_trust_level(cls, v: str | None) -> str | None:
        """校验可信度等级。"""
        if v is None:
            return v
        allowed = {"high", "medium", "low"}
        if v not in allowed:
            raise ValueError(f"可信度必须是 {allowed} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态。"""
        if v is None:
            return v
        allowed = {"active", "disabled", "error"}
        if v not in allowed:
            raise ValueError(f"状态必须是 {allowed} 之一")
        return v


class BGPDataSourceResponse(BGPDataSourceBase):
    """BGP 数据源响应。"""

    id: int
    status: str
    last_connected_at: datetime | None
    last_error: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# 观察点
# ──────────────────────────────────────────────


class ObservationPointBase(BaseModel):
    """观察点基础模式。"""

    name: str = Field(..., max_length=255, description="观察点名称")
    data_source_id: int = Field(..., description="所属数据源 ID")
    location: str | None = Field(None, max_length=255, description="观察点地理位置")
    collector_id: str | None = Field(None, max_length=100, description="采集器标识")
    ip_version: str = Field(default="dual", description="IP 版本：4/6/dual")
    status: str = Field(default="active", description="观察点状态")

    @field_validator("ip_version")
    @classmethod
    def validate_ip_version(cls, v: str) -> str:
        """校验 IP 版本。"""
        allowed = {"4", "6", "dual"}
        if v not in allowed:
            raise ValueError(f"IP 版本必须是 {allowed} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        allowed = {"active", "disabled"}
        if v not in allowed:
            raise ValueError(f"状态必须是 {allowed} 之一")
        return v


class ObservationPointCreate(ObservationPointBase):
    """创建观察点请求。"""


class ObservationPointUpdate(BaseModel):
    """更新观察点请求。"""

    name: str | None = Field(None, max_length=255, description="观察点名称")
    location: str | None = Field(None, max_length=255, description="观察点地理位置")
    collector_id: str | None = Field(None, max_length=100, description="采集器标识")
    ip_version: str | None = Field(None, description="IP 版本")
    status: str | None = Field(None, description="观察点状态")


class ObservationPointResponse(ObservationPointBase):
    """观察点响应。"""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# BGP 公告
# ──────────────────────────────────────────────


class BGPAnnouncementResponse(BaseModel):
    """BGP 公告响应。"""

    id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    origin_as: int | None
    as_path: list[int] | None
    next_hop: str | None
    communities: list[str] | None
    large_communities: list[str] | None
    med: int | None
    local_pref: int | None
    observation_point_id: int | None
    data_source_id: int | None
    timestamp: datetime
    address_family: int
    rpki_validation_status: str | None
    rpki_invalid_reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BGPAnnouncementQueryParams(BaseModel):
    """BGP 公告查询参数。"""

    prefix: str | None = Field(None, description="按前缀过滤（精确匹配）")
    origin_as: int | None = Field(None, description="按起源 AS 过滤")
    observation_point_id: int | None = Field(None, description="按观察点过滤")
    data_source_id: int | None = Field(None, description="按数据源过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    rpki_validation_status: str | None = Field(None, description="按 RPKI 验证状态过滤")
    limit: int = Field(default=100, ge=1, le=1000, description="返回记录数上限")
    skip: int = Field(default=0, ge=0, description="跳过记录数")


# ──────────────────────────────────────────────
# BGP 撤路
# ──────────────────────────────────────────────


class BGPWithdrawResponse(BaseModel):
    """BGP 撤路响应。"""

    id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    observation_point_id: int | None
    data_source_id: int | None
    timestamp: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BGPWithdrawQueryParams(BaseModel):
    """BGP 撤路查询参数。"""

    prefix: str | None = Field(None, description="按前缀过滤")
    observation_point_id: int | None = Field(None, description="按观察点过滤")
    data_source_id: int | None = Field(None, description="按数据源过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    limit: int = Field(default=100, ge=1, le=1000, description="返回记录数上限")
    skip: int = Field(default=0, ge=0, description="跳过记录数")


# ──────────────────────────────────────────────
# RIB 快照
# ──────────────────────────────────────────────


class BGPRibSnapshotResponse(BaseModel):
    """RIB 快照响应。"""

    id: int
    observation_point_id: int | None
    snapshot_time: datetime
    route_count: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# 设备适配器
# ──────────────────────────────────────────────


class DeviceAdapterBase(BaseModel):
    """设备适配器基础模式。"""

    name: str = Field(..., max_length=255, description="适配器名称")
    vendor: str = Field(
        ...,
        description="设备厂商：cisco/juniper/huawei/h3c/arista/nokia/frr/bird/openbgpd",
    )
    model: str | None = Field(None, max_length=255, description="设备型号")
    connection_type: str = Field(..., description="连接类型：snmp/netconf/restconf/gnmi/cli/bmp")
    endpoint: str = Field(..., max_length=500, description="设备端点")
    credentials: dict[str, Any] | None = Field(None, description="加密存储的凭据")
    capabilities: dict[str, Any] | None = Field(None, description="设备能力描述")

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str) -> str:
        """校验设备厂商。"""
        allowed = {
            "cisco",
            "juniper",
            "huawei",
            "h3c",
            "arista",
            "nokia",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"设备厂商必须是 {allowed} 之一")
        return v

    @field_validator("connection_type")
    @classmethod
    def validate_connection_type(cls, v: str) -> str:
        """校验连接类型。"""
        allowed = {"snmp", "netconf", "restconf", "gnmi", "cli", "bmp"}
        if v not in allowed:
            raise ValueError(f"连接类型必须是 {allowed} 之一")
        return v


class DeviceAdapterCreate(DeviceAdapterBase):
    """创建设备适配器请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class DeviceAdapterUpdate(BaseModel):
    """更新设备适配器请求。"""

    name: str | None = Field(None, max_length=255, description="适配器名称")
    model: str | None = Field(None, max_length=255, description="设备型号")
    endpoint: str | None = Field(None, max_length=500, description="设备端点")
    credentials: dict[str, Any] | None = Field(None, description="加密存储的凭据")
    capabilities: dict[str, Any] | None = Field(None, description="设备能力描述")
    status: str | None = Field(None, description="适配器状态")


class DeviceAdapterResponse(DeviceAdapterBase):
    """设备适配器响应。"""

    id: int
    status: str
    last_connected_at: datetime | None
    last_error: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# 数据源健康与统计
# ──────────────────────────────────────────────


class DataSourceHealthResponse(BaseModel):
    """数据源健康状态响应。"""

    source_id: int
    name: str
    status: str
    healthy: bool
    last_connected_at: datetime | None
    last_error: str | None
    trust_level: str


class BGPStatsResponse(BaseModel):
    """BGP 统计数据响应。"""

    total_data_sources: int = Field(description="数据源总数")
    active_data_sources: int = Field(description="活跃数据源数")
    total_observation_points: int = Field(description="观察点总数")
    total_announcements: int = Field(description="公告总数（热数据）")
    total_withdraws: int = Field(description="撤路总数（热数据）")
    total_device_adapters: int = Field(description="设备适配器总数")
    announcements_by_rpki_status: dict[str, int] = Field(
        default_factory=dict, description="按 RPKI 验证状态分组的公告数"
    )
