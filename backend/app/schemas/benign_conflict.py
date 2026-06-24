"""ROA 良性冲突相关 Pydantic 模式（请求与响应）。

包含良性冲突记录、维护窗口、清洗商授权、Anycast 节点的 CRUD 模式，
以及良性冲突分析结果与统计摘要。

注意：
    本模块不通过 ``app.schemas.__init__`` 注册（共享文件不可修改），
    使用方需直接 ``from app.schemas.benign_conflict import ...`` 显式导入。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ──────────────────────────────────────────────
# 枚举集合
# ──────────────────────────────────────────────


# 良性冲突类型
CONFLICT_TYPES = {
    "ddos_scrubbing",
    "anycast_expansion",
    "planned_maintenance",
    "resource_transfer",
    "data_source_delay",
    "customer_misconfig",
}

# 良性冲突记录状态
RECORD_STATUSES = {"suspected", "confirmed", "dismissed"}

# 维护窗口状态
MAINTENANCE_STATUSES = {
    "scheduled",
    "active",
    "completed",
    "cancelled",
}

# 清洗商授权状态
SCRUBBER_AUTH_STATUSES = {"active", "expired", "revoked"}

# Anycast 节点状态
ANYCAST_NODE_STATUSES = {"active", "inactive"}


# ──────────────────────────────────────────────
# 良性冲突记录
# ──────────────────────────────────────────────


class BenignConflictRecordBase(BaseModel):
    """良性冲突记录基础字段。"""

    conflict_type: str = Field(..., description="冲突类型")
    prefix: str = Field(..., description="关联的网络前缀")
    origin_as: int | None = Field(None, description="观测到的起源 AS 号")
    expected_origin_as: int | None = Field(None, description="期望的起源 AS 号")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度（0-1）")
    evidence: dict[str, Any] | None = Field(None, description="证据数据")
    recommendation: str | None = Field(None, description="处理建议")
    status: str = Field(default="suspected", description="状态：suspected/confirmed/dismissed")
    valid_until: datetime | None = Field(None, description="授权时间窗结束时间")
    related_work_order: str | None = Field(None, description="关联工单号")

    @field_validator("conflict_type")
    @classmethod
    def validate_conflict_type(cls, v: str) -> str:
        """校验冲突类型。"""
        if v not in CONFLICT_TYPES:
            raise ValueError(f"conflict_type 必须为 {CONFLICT_TYPES} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        if v not in RECORD_STATUSES:
            raise ValueError(f"status 必须为 {RECORD_STATUSES} 之一")
        return v


class BenignConflictRecordCreate(BenignConflictRecordBase):
    """创建良性冲突记录请求。"""

    alert_id: int | None = Field(None, description="关联告警 ID")
    tenant_id: int | None = Field(None, description="租户 ID")


class BenignConflictRecordUpdate(BaseModel):
    """更新良性冲突记录请求。"""

    confidence: float | None = Field(None, ge=0.0, le=1.0, description="置信度（0-1）")
    evidence: dict[str, Any] | None = Field(None, description="证据数据")
    recommendation: str | None = Field(None, description="处理建议")
    status: str | None = Field(None, description="状态")
    valid_until: datetime | None = Field(None, description="授权时间窗结束时间")
    related_work_order: str | None = Field(None, description="关联工单号")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态。"""
        if v is None:
            return v
        if v not in RECORD_STATUSES:
            raise ValueError(f"status 必须为 {RECORD_STATUSES} 之一")
        return v


class BenignConflictRecordResponse(BenignConflictRecordBase):
    """良性冲突记录响应。"""

    id: int
    alert_id: int | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BenignConflictRecordListResponse(BaseModel):
    """良性冲突记录列表响应（带分页信息）。"""

    items: list[BenignConflictRecordResponse]
    total: int
    skip: int
    limit: int


class BenignConflictQueryParams(BaseModel):
    """良性冲突查询参数。"""

    prefix: str | None = Field(None, description="按前缀过滤")
    origin_as: int | None = Field(None, description="按起源 AS 过滤")
    conflict_type: str | None = Field(None, description="按冲突类型过滤")
    status: str | None = Field(None, description="按状态过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


class BenignConflictStatusUpdate(BaseModel):
    """良性冲突状态更新请求。"""

    status: str = Field(..., description="新的状态")
    recommendation: str | None = Field(None, description="处理建议")
    related_work_order: str | None = Field(None, description="关联工单号")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        if v not in RECORD_STATUSES:
            raise ValueError(f"status 必须为 {RECORD_STATUSES} 之一")
        return v


# ──────────────────────────────────────────────
# 维护窗口
# ──────────────────────────────────────────────


class MaintenanceWindowBase(BaseModel):
    """维护窗口基础字段。"""

    name: str = Field(..., min_length=1, max_length=255, description="维护窗口名称")
    description: str | None = Field(None, description="维护描述")
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    prefixes: list[str] | None = Field(None, description="受影响前缀列表")
    asns: list[int] | None = Field(None, description="受影响 ASN 列表")
    approved_by: int | None = Field(None, description="审批人用户 ID")
    status: str = Field(
        default="scheduled",
        description="状态：scheduled/active/completed/cancelled",
    )
    work_order_id: str | None = Field(None, description="关联工单号")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        if v not in MAINTENANCE_STATUSES:
            raise ValueError(f"status 必须为 {MAINTENANCE_STATUSES} 之一")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> MaintenanceWindowBase:
        """校验时间范围：结束时间必须晚于开始时间。"""
        if self.end_time <= self.start_time:
            raise ValueError("end_time 必须晚于 start_time")
        return self


class MaintenanceWindowCreate(MaintenanceWindowBase):
    """创建维护窗口请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class MaintenanceWindowUpdate(BaseModel):
    """更新维护窗口请求。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="维护窗口名称")
    description: str | None = Field(None, description="维护描述")
    start_time: datetime | None = Field(None, description="开始时间")
    end_time: datetime | None = Field(None, description="结束时间")
    prefixes: list[str] | None = Field(None, description="受影响前缀列表")
    asns: list[int] | None = Field(None, description="受影响 ASN 列表")
    approved_by: int | None = Field(None, description="审批人用户 ID")
    status: str | None = Field(None, description="状态")
    work_order_id: str | None = Field(None, description="关联工单号")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态。"""
        if v is None:
            return v
        if v not in MAINTENANCE_STATUSES:
            raise ValueError(f"status 必须为 {MAINTENANCE_STATUSES} 之一")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> MaintenanceWindowUpdate:
        """校验时间范围（若同时提供起止时间）。"""
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time 必须晚于 start_time")
        return self


class MaintenanceWindowResponse(MaintenanceWindowBase):
    """维护窗口响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceWindowListResponse(BaseModel):
    """维护窗口列表响应（带分页信息）。"""

    items: list[MaintenanceWindowResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# 清洗商授权
# ──────────────────────────────────────────────


class ScrubberAuthorizationBase(BaseModel):
    """清洗商授权基础字段。"""

    scrubber_asn: int = Field(..., ge=1, le=4294967295, description="清洗商 AS 号")
    customer_prefix: str = Field(..., description="客户前缀（CIDR）")
    customer_asn: int = Field(..., ge=1, le=4294967295, description="客户 AS 号")
    authorized_at: datetime = Field(..., description="授权时间")
    expires_at: datetime = Field(..., description="授权截止时间")
    work_order_id: str | None = Field(None, description="关联工单号")
    status: str = Field(default="active", description="状态：active/expired/revoked")
    contact_info: dict[str, Any] | None = Field(None, description="联系人信息")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        if v not in SCRUBBER_AUTH_STATUSES:
            raise ValueError(f"status 必须为 {SCRUBBER_AUTH_STATUSES} 之一")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> ScrubberAuthorizationBase:
        """校验时间范围：截止时间必须晚于授权时间。"""
        if self.expires_at <= self.authorized_at:
            raise ValueError("expires_at 必须晚于 authorized_at")
        return self


class ScrubberAuthorizationCreate(ScrubberAuthorizationBase):
    """创建清洗商授权请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class ScrubberAuthorizationUpdate(BaseModel):
    """更新清洗商授权请求。"""

    authorized_at: datetime | None = Field(None, description="授权时间")
    expires_at: datetime | None = Field(None, description="授权截止时间")
    work_order_id: str | None = Field(None, description="关联工单号")
    status: str | None = Field(None, description="状态")
    contact_info: dict[str, Any] | None = Field(None, description="联系人信息")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态。"""
        if v is None:
            return v
        if v not in SCRUBBER_AUTH_STATUSES:
            raise ValueError(f"status 必须为 {SCRUBBER_AUTH_STATUSES} 之一")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> ScrubberAuthorizationUpdate:
        """校验时间范围（若同时提供起止时间）。"""
        if (
            self.authorized_at is not None
            and self.expires_at is not None
            and self.expires_at <= self.authorized_at
        ):
            raise ValueError("expires_at 必须晚于 authorized_at")
        return self


class ScrubberAuthorizationResponse(ScrubberAuthorizationBase):
    """清洗商授权响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScrubberAuthorizationListResponse(BaseModel):
    """清洗商授权列表响应（带分页信息）。"""

    items: list[ScrubberAuthorizationResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# Anycast 节点
# ──────────────────────────────────────────────


class AnycastNodeBase(BaseModel):
    """Anycast 节点基础字段。"""

    node_asn: int = Field(..., ge=1, le=4294967295, description="Anycast 节点 AS 号")
    prefix: str = Field(..., description="Anycast 前缀（CIDR）")
    region: str | None = Field(None, description="地域")
    site: str | None = Field(None, description="机房")
    business_tag: str | None = Field(None, description="业务标签")
    registered_at: datetime = Field(..., description="登记时间")
    status: str = Field(default="active", description="状态：active/inactive")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        if v not in ANYCAST_NODE_STATUSES:
            raise ValueError(f"status 必须为 {ANYCAST_NODE_STATUSES} 之一")
        return v


class AnycastNodeCreate(AnycastNodeBase):
    """创建 Anycast 节点请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class AnycastNodeUpdate(BaseModel):
    """更新 Anycast 节点请求。"""

    region: str | None = Field(None, description="地域")
    site: str | None = Field(None, description="机房")
    business_tag: str | None = Field(None, description="业务标签")
    registered_at: datetime | None = Field(None, description="登记时间")
    status: str | None = Field(None, description="状态")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态。"""
        if v is None:
            return v
        if v not in ANYCAST_NODE_STATUSES:
            raise ValueError(f"status 必须为 {ANYCAST_NODE_STATUSES} 之一")
        return v


class AnycastNodeResponse(AnycastNodeBase):
    """Anycast 节点响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnycastNodeListResponse(BaseModel):
    """Anycast 节点列表响应（带分页信息）。"""

    items: list[AnycastNodeResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# 良性冲突分析结果
# ──────────────────────────────────────────────


class BenignConflictAnalysisResult(BaseModel):
    """良性冲突分析结果。

    由 ``BenignConflictDetector.analyze`` 返回，描述对一条告警的
    良性冲突分析结论，包含冲突类型、置信度、证据与处理建议。

    注意：良性冲突识别只降低误报优先级，不能替代安全验证。
    """

    conflict_type: str | None = Field(None, description="识别到的冲突类型，未识别为良性时为 None")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="置信度（0-1）",
    )
    evidence: dict[str, Any] = Field(default_factory=dict, description="证据数据")
    recommendation: str = Field(default="", description="处理建议")
    is_benign: bool = Field(
        default=False,
        description=(
            "是否判定为良性冲突。True 表示疑似或确认良性，"
            "可降低告警优先级；False 表示未识别为良性，需保持原有处置流程。"
        ),
    )

    @field_validator("conflict_type")
    @classmethod
    def validate_conflict_type(cls, v: str | None) -> str | None:
        """校验冲突类型。"""
        if v is None:
            return v
        if v not in CONFLICT_TYPES:
            raise ValueError(f"conflict_type 必须为 {CONFLICT_TYPES} 之一")
        return v


class BenignConflictAnalyzeRequest(BaseModel):
    """良性冲突分析请求。

    支持两种输入：
    1. 提供 ``alert_id``：分析指定告警
    2. 提供 ``prefix`` + ``origin_as``：分析指定前缀与起源 AS
    """

    alert_id: int | None = Field(None, description="告警 ID")
    prefix: str | None = Field(None, description="网络前缀")
    origin_as: int | None = Field(None, description="起源 AS 号")

    @model_validator(mode="after")
    def validate_input(self) -> BenignConflictAnalyzeRequest:
        """校验输入：必须提供 alert_id 或 prefix+origin_as。"""
        if self.alert_id is not None:
            return self
        if self.prefix is not None and self.origin_as is not None:
            return self
        raise ValueError("必须提供 alert_id，或同时提供 prefix 与 origin_as")


# ──────────────────────────────────────────────
# 良性冲突统计摘要
# ──────────────────────────────────────────────


class BenignConflictTypeSummary(BaseModel):
    """按冲突类型分组的统计摘要。"""

    conflict_type: str = Field(..., description="冲突类型")
    count: int = Field(0, description="记录数")
    confirmed_count: int = Field(0, description="已确认数")
    suspected_count: int = Field(0, description="疑似数")
    dismissed_count: int = Field(0, description="已驳回数")
    avg_confidence: float = Field(0.0, description="平均置信度")


class BenignConflictSummary(BaseModel):
    """良性冲突统计摘要。"""

    total: int = Field(0, description="总记录数")
    confirmed: int = Field(0, description="已确认数")
    suspected: int = Field(0, description="疑似数")
    dismissed: int = Field(0, description="已驳回数")
    by_type: list[BenignConflictTypeSummary] = Field(
        default_factory=list, description="按冲突类型分组的统计"
    )
    recent_24h: int = Field(0, description="最近 24 小时新增数")


__all__ = [
    "ANYCAST_NODE_STATUSES",
    "AnycastNodeBase",
    "AnycastNodeCreate",
    "AnycastNodeListResponse",
    "AnycastNodeResponse",
    "AnycastNodeUpdate",
    "BenignConflictAnalyzeRequest",
    "BenignConflictAnalysisResult",
    "BenignConflictQueryParams",
    "BenignConflictRecordBase",
    "BenignConflictRecordCreate",
    "BenignConflictRecordListResponse",
    "BenignConflictRecordResponse",
    "BenignConflictRecordUpdate",
    "BenignConflictStatusUpdate",
    "BenignConflictSummary",
    "BenignConflictTypeSummary",
    "CONFLICT_TYPES",
    "MAINTENANCE_STATUSES",
    "MaintenanceWindowBase",
    "MaintenanceWindowCreate",
    "MaintenanceWindowListResponse",
    "MaintenanceWindowResponse",
    "MaintenanceWindowUpdate",
    "RECORD_STATUSES",
    "SCRUBBER_AUTH_STATUSES",
    "ScrubberAuthorizationBase",
    "ScrubberAuthorizationCreate",
    "ScrubberAuthorizationListResponse",
    "ScrubberAuthorizationResponse",
    "ScrubberAuthorizationUpdate",
]
