"""驾驶舱与详情视图相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ──────────────────────────────────────────────
# 总览驾驶舱
# ──────────────────────────────────────────────


class PrefixStats(BaseModel):
    """前缀统计信息。"""

    total: int = Field(default=0, description="前缀总数")
    active: int = Field(default=0, description="活跃前缀数")
    by_importance: dict[str, int] = Field(
        default_factory=dict, description="按重要度分组：critical/important/normal/low"
    )
    by_family: dict[str, int] = Field(default_factory=dict, description="按协议族分组：ipv4/ipv6")


class ASNStats(BaseModel):
    """ASN 统计信息。"""

    total: int = Field(default=0, description="ASN 总数")
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="按关系类型分组：own/customer/provider/peer 等",
    )


class ROACoverage(BaseModel):
    """ROA 覆盖率统计。"""

    total_prefixes: int = Field(default=0, description="前缀总数")
    prefixes_with_roa: int = Field(default=0, description="有 ROA 覆盖的前缀数")
    coverage_rate: float = Field(default=0.0, description="覆盖率（0-1）")
    missing_count: int = Field(default=0, description="未覆盖前缀数")


class ValidationDistribution(BaseModel):
    """BGP 公告 RPKI 验证状态分布。"""

    valid: int = Field(default=0, description="Valid 公告数")
    invalid: int = Field(default=0, description="Invalid 公告数")
    not_found: int = Field(default=0, description="NotFound 公告数")
    total: int = Field(default=0, description="公告总数")


class IncidentStats(BaseModel):
    """事件统计信息。"""

    p0: int = Field(default=0, description="P0 事件数")
    p1: int = Field(default=0, description="P1 事件数")
    p2: int = Field(default=0, description="P2 事件数")
    p3: int = Field(default=0, description="P3 事件数")
    p4: int = Field(default=0, description="P4 事件数")
    total_open: int = Field(default=0, description="未关闭事件总数")


class RPKICacheStatus(BaseModel):
    """RPKI 缓存状态。"""

    cache_count: int = Field(default=0, description="缓存实例数")
    last_update: datetime | None = Field(None, description="最后更新时间")
    vrp_count: int = Field(default=0, description="VRP 总数")
    status: str = Field(default="unknown", description="整体状态：healthy/stale/unknown")


class BGPSourceStatus(BaseModel):
    """BGP 数据源状态。"""

    active: int = Field(default=0, description="活跃数据源数")
    error: int = Field(default=0, description="异常数据源数")
    total: int = Field(default=0, description="数据源总数")
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="按类型分组：ripe_ris/routeviews/route_server 等",
    )


class RiskTrendPoint(BaseModel):
    """风险趋势数据点。"""

    date: str = Field(..., description="日期（YYYY-MM-DD）")
    alert_count: int = Field(default=0, description="告警数量")
    incident_count: int = Field(default=0, description="事件数量")


class DashboardOverview(BaseModel):
    """驾驶舱总览数据。"""

    prefix_stats: PrefixStats = Field(default_factory=PrefixStats)
    asn_stats: ASNStats = Field(default_factory=ASNStats)
    roa_coverage: ROACoverage = Field(default_factory=ROACoverage)
    validation_distribution: ValidationDistribution = Field(default_factory=ValidationDistribution)
    incident_stats: IncidentStats = Field(default_factory=IncidentStats)
    rpki_cache_status: RPKICacheStatus = Field(default_factory=RPKICacheStatus)
    bgp_source_status: BGPSourceStatus = Field(default_factory=BGPSourceStatus)
    risk_trend: list[RiskTrendPoint] = Field(default_factory=list, description="最近 7 天风险趋势")


# ──────────────────────────────────────────────
# 前缀详情
# ──────────────────────────────────────────────


class PrefixAssetInfo(BaseModel):
    """前缀资产属性。"""

    id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    status: str
    importance: str
    business_service: str | None = None
    region: str | None = None
    site: str | None = None
    cloud_zone: str | None = None
    customer_id: int | None = None
    tags: list[str] | None = None
    description: str | None = None
    registered_at: datetime | None = None
    expired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthorizedOrigin(BaseModel):
    """合法 origin 信息（来自 ROA）。"""

    roa_id: int
    origin_as: int
    prefix: str
    max_length: int | None = None
    tal_id: int | None = None
    status: str
    not_before: datetime | None = None
    not_after: datetime | None = None


class CurrentAnnouncement(BaseModel):
    """当前 BGP 公告。"""

    id: int
    prefix: str
    origin_as: int | None = None
    as_path: list[int] | None = None
    next_hop: str | None = None
    observation_point_id: int | None = None
    data_source_id: int | None = None
    timestamp: datetime
    rpki_validation_status: str | None = None
    rpki_invalid_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MatchedVRP(BaseModel):
    """匹配的 VRP。"""

    id: int
    prefix: str
    origin_as: int
    max_length: int | None = None
    tal_id: int | None = None
    trust_anchor: str | None = None
    validation_status: str

    model_config = ConfigDict(from_attributes=True)


class PrefixAlertItem(BaseModel):
    """前缀关联告警。"""

    id: int
    alert_type: str
    severity: str
    title: str
    description: str | None = None
    status: str
    risk_score: float
    confidence: float
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrefixDetail(BaseModel):
    """前缀详情。"""

    asset: PrefixAssetInfo
    authorized_origins: list[AuthorizedOrigin] = Field(default_factory=list)
    current_announcements: list[CurrentAnnouncement] = Field(default_factory=list)
    as_paths: list[list[int]] = Field(default_factory=list, description="去重后的 AS_PATH 列表")
    matched_roas: list[AuthorizedOrigin] = Field(default_factory=list)
    matched_vrps: list[MatchedVRP] = Field(default_factory=list)
    irr_info: dict[str, Any] | None = Field(None, description="IRR 信息（占位，TODO）")
    history: list[dict[str, Any]] = Field(
        default_factory=list, description="历史状态（占位，从 ClickHouse 查询）"
    )
    alerts: list[PrefixAlertItem] = Field(default_factory=list)
    business_impact: str | None = Field(None, description="业务影响（业务归属）")
    recommendations: list[str] = Field(default_factory=list, description="操作建议")


# ──────────────────────────────────────────────
# ASN 详情
# ──────────────────────────────────────────────


class ASNAssetInfo(BaseModel):
    """ASN 资产属性。"""

    id: int
    asn: int
    name: str
    asn_type: str
    status: str
    risk_profile: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    noc_phone: str | None = None
    emergency_contact: str | None = None
    relationship_tags: list[str] | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ASNPrefixItem(BaseModel):
    """ASN 关联前缀。"""

    id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    status: str
    importance: str
    business_service: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ASNAlertItem(BaseModel):
    """ASN 关联告警。"""

    id: int
    alert_type: str
    severity: str
    prefix: str
    title: str
    description: str | None = None
    status: str
    risk_score: float
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ASNDetail(BaseModel):
    """ASN 详情。"""

    asset: ASNAssetInfo
    related_prefixes: list[ASNPrefixItem] = Field(default_factory=list)
    upstream: list[int] = Field(
        default_factory=list, description="上游 AS（占位，从 BGP AS_PATH 分析）"
    )
    downstream: list[int] = Field(default_factory=list, description="下游 AS（占位）")
    peers: list[int] = Field(default_factory=list, description="对等 AS（占位）")
    history_paths: list[dict[str, Any]] = Field(
        default_factory=list, description="历史路径（占位）"
    )
    alerts: list[ASNAlertItem] = Field(default_factory=list)
    risk_profile: str | None = Field(None, description="风险画像")


# ──────────────────────────────────────────────
# 事件时间线
# ──────────────────────────────────────────────


class IncidentTimelineItem(BaseModel):
    """事件时间线条目。"""

    timestamp: datetime
    event_type: str = Field(..., description="事件类型")
    description: str = Field(..., description="事件描述")
    operator: str | None = Field(None, description="操作人")


class IncidentBasicInfo(BaseModel):
    """事件基本信息。"""

    id: int
    title: str
    description: str | None = None
    severity: str
    status: str
    affected_prefixes: list[str] | None = None
    affected_asns: list[int] | None = None
    assigned_to: int | None = None
    root_cause: str | None = None
    resolution: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentTimeline(BaseModel):
    """事件时间线。"""

    incident: IncidentBasicInfo
    timeline: list[IncidentTimelineItem] = Field(default_factory=list)
    related_alerts: list[dict[str, Any]] = Field(default_factory=list)
    impact_scope: dict[str, Any] | None = Field(None, description="影响范围摘要")
    recommendations: list[str] = Field(default_factory=list, description="处置建议")
    root_cause_analysis: str | None = Field(None, description="根因分析")


__all__ = [
    "ASNAlertItem",
    "ASNAssetInfo",
    "ASNDetail",
    "ASNPrefixItem",
    "ASNStats",
    "AuthorizedOrigin",
    "BGPSourceStatus",
    "CurrentAnnouncement",
    "DashboardOverview",
    "IncidentBasicInfo",
    "IncidentStats",
    "IncidentTimeline",
    "IncidentTimelineItem",
    "MatchedVRP",
    "PrefixAlertItem",
    "PrefixAssetInfo",
    "PrefixDetail",
    "PrefixStats",
    "ROACoverage",
    "RPKICacheStatus",
    "RiskTrendPoint",
    "ValidationDistribution",
]
