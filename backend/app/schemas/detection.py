"""BGP 路由安全检测引擎相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ──────────────────────────────────────────────
# 检测规则
# ──────────────────────────────────────────────


# 规则类型枚举
RULE_TYPES = {
    "hijack",
    "subprefix_hijack",
    "moas",
    "route_leak",
    "path_anomaly",
    "withdraw_flap",
    "rpki_invalid",
}

# 严重等级枚举
SEVERITY_LEVELS = {"P0", "P1", "P2", "P3", "P4"}


class DetectionRuleBase(BaseModel):
    """检测规则基础模式。"""

    name: str = Field(..., max_length=255, description="规则名称")
    code: str = Field(..., max_length=100, description="规则唯一编码")
    description: str | None = Field(None, description="规则描述")
    rule_type: str = Field(..., description="规则类型")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=100, ge=0, description="优先级（数值越小越高）")
    conditions: dict[str, Any] | None = Field(None, description="规则条件配置")
    thresholds: dict[str, Any] | None = Field(None, description="阈值配置")
    whitelist: dict[str, Any] | None = Field(None, description="白名单配置")
    scope: dict[str, Any] | None = Field(None, description="生效范围")
    severity: str = Field(default="P3", description="严重等级：P0/P1/P2/P3/P4")

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, v: str) -> str:
        """校验规则类型。"""
        if v not in RULE_TYPES:
            raise ValueError(f"规则类型必须是 {RULE_TYPES} 之一")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """校验严重等级。"""
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"严重等级必须是 {SEVERITY_LEVELS} 之一")
        return v


class DetectionRuleCreate(DetectionRuleBase):
    """创建检测规则请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class DetectionRuleUpdate(BaseModel):
    """更新检测规则请求。"""

    name: str | None = Field(None, max_length=255, description="规则名称")
    description: str | None = Field(None, description="规则描述")
    enabled: bool | None = Field(None, description="是否启用")
    priority: int | None = Field(None, ge=0, description="优先级")
    conditions: dict[str, Any] | None = Field(None, description="规则条件配置")
    thresholds: dict[str, Any] | None = Field(None, description="阈值配置")
    whitelist: dict[str, Any] | None = Field(None, description="白名单配置")
    scope: dict[str, Any] | None = Field(None, description="生效范围")
    severity: str | None = Field(None, description="严重等级")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        """校验严重等级。"""
        if v is None:
            return v
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"严重等级必须是 {SEVERITY_LEVELS} 之一")
        return v


class DetectionRuleResponse(DetectionRuleBase):
    """检测规则响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# 告警
# ──────────────────────────────────────────────


ALERT_STATUSES = {
    "new",
    "confirmed",
    "assigned",
    "resolved",
    "closed",
    "false_positive",
}


class AlertResponse(BaseModel):
    """告警响应。"""

    id: int
    rule_id: int | None
    alert_type: str
    severity: str
    prefix: str
    origin_as: int | None
    as_path: list[int] | None
    observation_point_id: int | None
    title: str
    description: str | None
    evidence: dict[str, Any] | None
    risk_score: float
    confidence: float
    status: str
    is_benign_conflict: bool
    benign_conflict_type: str | None
    incident_id: int | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertQueryParams(BaseModel):
    """告警查询参数。"""

    prefix: str | None = Field(None, description="按前缀过滤")
    origin_as: int | None = Field(None, description="按起源 AS 过滤")
    severity: str | None = Field(None, description="按严重等级过滤")
    status: str | None = Field(None, description="按处置状态过滤")
    alert_type: str | None = Field(None, description="按告警类型过滤")
    incident_id: int | None = Field(None, description="按关联事件过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


class AlertStatusUpdate(BaseModel):
    """告警状态更新请求。"""

    status: str = Field(..., description="新的处置状态")
    is_benign_conflict: bool | None = Field(None, description="是否标记为良性冲突")
    benign_conflict_type: str | None = Field(None, description="良性冲突类型")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验处置状态。"""
        if v not in ALERT_STATUSES:
            raise ValueError(f"处置状态必须是 {ALERT_STATUSES} 之一")
        return v


class AlertAssignRequest(BaseModel):
    """告警关联事件请求。"""

    incident_id: int = Field(..., description="关联的事件 ID")


# ──────────────────────────────────────────────
# 事件
# ──────────────────────────────────────────────


INCIDENT_STATUSES = {
    "open",
    "investigating",
    "mitigating",
    "resolved",
    "closed",
}


class IncidentCreate(BaseModel):
    """创建事件请求。"""

    title: str = Field(..., max_length=500, description="事件标题")
    description: str | None = Field(None, description="事件描述")
    severity: str = Field(default="P3", description="严重等级")
    alert_ids: list[int] | None = Field(None, description="关联告警 ID 列表")
    affected_prefixes: list[str] | None = Field(None, description="受影响前缀列表")
    affected_asns: list[int] | None = Field(None, description="受影响 ASN 列表")
    tenant_id: int | None = Field(None, description="租户 ID")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """校验严重等级。"""
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"严重等级必须是 {SEVERITY_LEVELS} 之一")
        return v


class IncidentUpdate(BaseModel):
    """更新事件请求。"""

    title: str | None = Field(None, max_length=500, description="事件标题")
    description: str | None = Field(None, description="事件描述")
    severity: str | None = Field(None, description="严重等级")
    status: str | None = Field(None, description="事件状态")
    affected_prefixes: list[str] | None = Field(None, description="受影响前缀列表")
    affected_asns: list[int] | None = Field(None, description="受影响 ASN 列表")
    root_cause: str | None = Field(None, description="根因分析")
    resolution: str | None = Field(None, description="处置结论")
    evidence: dict[str, Any] | None = Field(None, description="事件证据")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        """校验严重等级。"""
        if v is None:
            return v
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"严重等级必须是 {SEVERITY_LEVELS} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验事件状态。"""
        if v is None:
            return v
        if v not in INCIDENT_STATUSES:
            raise ValueError(f"事件状态必须是 {INCIDENT_STATUSES} 之一")
        return v


class IncidentResponse(BaseModel):
    """事件响应。"""

    id: int
    title: str
    description: str | None
    severity: str
    status: str
    alert_ids: list[int] | None
    affected_prefixes: list[str] | None
    affected_asns: list[int] | None
    assigned_to: int | None
    root_cause: str | None
    resolution: str | None
    evidence: dict[str, Any] | None
    timeline: list[dict[str, Any]] | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentQueryParams(BaseModel):
    """事件查询参数。"""

    status: str | None = Field(None, description="按状态过滤")
    severity: str | None = Field(None, description="按严重等级过滤")
    assigned_to: int | None = Field(None, description="按分派用户过滤")
    prefix: str | None = Field(None, description="按受影响前缀过滤")
    asn: int | None = Field(None, description="按受影响 ASN 过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


class IncidentAssignRequest(BaseModel):
    """事件分派请求。"""

    user_id: int = Field(..., description="分派给的用户 ID")


class IncidentCloseRequest(BaseModel):
    """事件关闭请求。"""

    resolution: str = Field(..., description="处置结论")


class TimelineEvent(BaseModel):
    """事件时间线条目。"""

    timestamp: datetime = Field(..., description="事件时间")
    event_type: str = Field(..., description="事件类型")
    description: str = Field(..., description="事件描述")
    operator: str | None = Field(None, description="操作人")


# ──────────────────────────────────────────────
# 风险评分
# ──────────────────────────────────────────────


class RiskScoreResponse(BaseModel):
    """风险评分响应。"""

    id: int
    alert_id: int | None
    incident_id: int | None
    total_score: float
    asset_importance_score: float
    asset_importance_factors: dict[str, Any] | None
    rpki_evidence_score: float
    rpki_evidence_factors: dict[str, Any] | None
    bgp_propagation_score: float
    bgp_propagation_factors: dict[str, Any] | None
    authorization_score: float
    authorization_factors: dict[str, Any] | None
    historical_baseline_score: float
    historical_factors: dict[str, Any] | None
    external_risk_score: float
    external_risk_factors: dict[str, Any] | None
    confidence: float
    recommended_actions: list[dict[str, Any]] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# 检测结果
# ──────────────────────────────────────────────


class DetectionResult(BaseModel):
    """通用检测结果。"""

    alert_type: str = Field(..., description="告警类型")
    severity: str = Field(..., description="严重等级")
    description: str = Field(..., description="检测描述")
    evidence: dict[str, Any] = Field(default_factory=dict, description="证据数据")
    risk_score: float = Field(default=0.0, description="风险评分")
    confidence: float = Field(default=0.0, description="置信度")
    is_detected: bool = Field(default=False, description="是否检测到异常")


class HijackDetectionResult(DetectionResult):
    """源 AS 劫持检测结果。"""

    authorized_origin_as: int | None = Field(None, description="授权的起源 AS")
    detected_origin_as: int | None = Field(None, description="检测到的起源 AS")
    rpki_validation_status: str | None = Field(None, description="RPKI 验证状态")
    propagation_scope: int = Field(default=0, description="传播范围（观察点数量）")


class SubprefixHijackResult(DetectionResult):
    """子前缀劫持检测结果。"""

    parent_prefix: str | None = Field(None, description="父前缀")
    subprefix: str | None = Field(None, description="子前缀")
    max_length_allowed: int | None = Field(None, description="允许的最大前缀长度")
    traffic_attraction_risk: str | None = Field(None, description="流量吸引风险等级")


class MOASDetectionResult(DetectionResult):
    """MOAS 检测结果。"""

    origin_as_list: list[int] = Field(default_factory=list, description="所有起源 AS 列表")
    moas_type: str | None = Field(
        None,
        description=("MOAS 类型：authorized_multi_origin/anycast/managed/scrubber/unknown"),
    )


class RouteLeakDetectionResult(DetectionResult):
    """路由泄露检测结果。"""

    leak_type: str | None = Field(
        None,
        description=("泄露类型：customer_to_provider/provider_to_customer/peer_to_peer/lateral"),
    )
    leak_path: list[int] = Field(default_factory=list, description="泄露路径 AS 列表")


class PathAnomalyResult(DetectionResult):
    """路径异常检测结果。"""

    anomaly_type: str | None = Field(
        None,
        description=(
            "异常类型：path_mutation/abnormal_transit/path_elongation/blackhole_risk/abnormal_geo"
        ),
    )
    baseline_path: list[int] | None = Field(None, description="基线 AS 路径")
    observed_path: list[int] | None = Field(None, description="观测 AS 路径")


class WithdrawFlapResult(DetectionResult):
    """撤路与震荡检测结果。"""

    withdraw_count: int = Field(default=0, description="撤路次数")
    announce_count: int = Field(default=0, description="公告次数")
    affected_observation_points: int = Field(default=0, description="受影响观察点数")
    flap_rate: float = Field(default=0.0, description="震荡频率（次/分钟）")


class RPKIInvalidResult(DetectionResult):
    """RPKI Invalid 传播检测结果。"""

    invalid_reason: str | None = Field(None, description="RPKI Invalid 原因")
    propagation_count: int = Field(default=0, description="传播该 Invalid 路由的观察点数")
    propagation_points: list[int] = Field(
        default_factory=list, description="传播 Invalid 的观察点 ID 列表"
    )


# ──────────────────────────────────────────────
# 手动扫描请求
# ──────────────────────────────────────────────


class ScanRequest(BaseModel):
    """手动触发检测扫描请求。"""

    prefix: str | None = Field(None, description="待扫描的网络前缀")
    origin_as: int | None = Field(None, description="待扫描的起源 AS")
    as_path: list[int] | None = Field(None, description="AS 路径")
    observation_point_id: int | None = Field(None, description="观察点 ID")
    rule_types: list[str] | None = Field(
        None, description="指定执行的规则类型列表（为空则全部执行）"
    )


class ScanResponse(BaseModel):
    """手动扫描响应。"""

    total_rules_executed: int = Field(0, description="执行的规则总数")
    results: list[DetectionResult] = Field(default_factory=list, description="检测结果列表")
    alerts_created: int = Field(default=0, description="生成的告警数")


__all__ = [
    "ALERT_STATUSES",
    "AlertAssignRequest",
    "AlertQueryParams",
    "AlertResponse",
    "AlertStatusUpdate",
    "DetectionResult",
    "DetectionRuleBase",
    "DetectionRuleCreate",
    "DetectionRuleResponse",
    "DetectionRuleUpdate",
    "HijackDetectionResult",
    "INCIDENT_STATUSES",
    "IncidentAssignRequest",
    "IncidentCloseRequest",
    "IncidentCreate",
    "IncidentQueryParams",
    "IncidentResponse",
    "IncidentUpdate",
    "MOASDetectionResult",
    "PathAnomalyResult",
    "RPKIInvalidResult",
    "RULE_TYPES",
    "RiskScoreResponse",
    "RouteLeakDetectionResult",
    "ScanRequest",
    "ScanResponse",
    "SEVERITY_LEVELS",
    "SubprefixHijackResult",
    "TimelineEvent",
    "WithdrawFlapResult",
]
