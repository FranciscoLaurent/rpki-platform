"""ROA 生命周期管理相关 Pydantic 模式（请求与响应）。

包含 ROA 查询、详情、缺失检测、冲突检测、maxLength 风险检查、
ROA 创建建议与变更影响评估等模式。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bgp import BGPAnnouncementResponse
from app.schemas.rpki import ROAResponse, VRPResponse


# ──────────────────────────────────────────────
# ROA 查询
# ──────────────────────────────────────────────


class ROAQueryParams(BaseModel):
    """ROA 查询参数。"""

    prefix: str | None = Field(None, description="按前缀过滤（精确匹配）")
    origin_as: int | None = Field(None, description="按起源 AS 过滤")
    max_length: int | None = Field(None, description="按最大前缀长度过滤")
    status: str | None = Field(
        None, description="按 ROA 状态过滤：valid/expired/revoked"
    )
    tal_id: int | None = Field(None, description="按 TAL ID 过滤")
    page: int = Field(default=1, ge=1, description="页码（从 1 开始）")
    page_size: int = Field(
        default=50, ge=1, le=200, description="每页记录数"
    )


# ──────────────────────────────────────────────
# ROA 详情
# ──────────────────────────────────────────────


class ROADetailResponse(ROAResponse):
    """ROA 详情响应，包含关联的 BGP 公告与 VRP 列表。"""

    bgp_announcements: list[BGPAnnouncementResponse] = Field(
        default_factory=list, description="关联的 BGP 公告列表"
    )
    vrps: list[VRPResponse] = Field(
        default_factory=list, description="关联的 VRP 列表"
    )


# ──────────────────────────────────────────────
# ROA 列表响应
# ──────────────────────────────────────────────


class ROAListResponse(BaseModel):
    """ROA 列表响应（带分页信息）。"""

    items: list[ROAResponse] = Field(default_factory=list, description="ROA 列表")
    total: int = Field(0, description="总记录数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(50, description="每页记录数")


# ──────────────────────────────────────────────
# ROA 缺失检测
# ──────────────────────────────────────────────


class ROAMissingCheckResult(BaseModel):
    """ROA 缺失检测结果。

    表示一个已公告的前缀在 ROA 数据库中的覆盖情况。
    """

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    has_roa: bool = Field(..., description="是否存在匹配的 ROA")
    has_vrp: bool = Field(..., description="是否存在匹配的 VRP")
    validation_status: str = Field(
        ..., description="BGP 公告的 RPKI 验证状态：valid/invalid/not_found"
    )
    importance: str | None = Field(
        None, description="前缀重要度：critical/important/normal/low"
    )
    business_service: str | None = Field(None, description="业务归属")
    customer_id: int | None = Field(None, description="关联客户 ID")


class ROAMissingCheckResponse(BaseModel):
    """ROA 缺失检测响应。"""

    items: list[ROAMissingCheckResult] = Field(
        default_factory=list, description="缺失检测结果列表"
    )
    total: int = Field(0, description="总检测前缀数")
    missing_count: int = Field(0, description="缺失 ROA 的前缀数")
    coverage_rate: float = Field(
        0.0, description="ROA 覆盖率（0-1）"
    )


# ──────────────────────────────────────────────
# ROA 冲突检测
# ──────────────────────────────────────────────


class ROAConflictCheckResult(BaseModel):
    """ROA 冲突检测结果。

    表示一个前缀存在 ROA 冲突的情况。
    """

    prefix: str = Field(..., description="网络前缀")
    origin_as: int | None = Field(
        None, description="实际公告的起源 AS 号（如有）"
    )
    conflicting_roas: list[ROAResponse] = Field(
        default_factory=list, description="冲突的 ROA 列表"
    )
    conflict_type: str = Field(
        ...,
        description=(
            "冲突类型：multiple_origin_as（同前缀多 AS 授权）、"
            "roa_bgp_mismatch（ROA 与实际公告不匹配）、"
            "overlapping_authorization（重叠授权）"
        ),
    )
    description: str = Field(
        "", description="冲突描述"
    )


class ROAConflictCheckResponse(BaseModel):
    """ROA 冲突检测响应。"""

    items: list[ROAConflictCheckResult] = Field(
        default_factory=list, description="冲突检测结果列表"
    )
    total: int = Field(0, description="检测到的冲突数")


# ──────────────────────────────────────────────
# maxLength 风险检查
# ──────────────────────────────────────────────


class MaxLengthRiskResult(BaseModel):
    """maxLength 风险检查结果。

    分析 ROA 的 maxLength 设置是否过宽，可能导致被劫持。
    """

    roa_id: int = Field(..., description="ROA ID")
    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    current_max_length: int | None = Field(
        None, description="当前 ROA 的 maxLength"
    )
    recommended_max_length: int = Field(
        ..., description="建议的 maxLength（基于实际公告）"
    )
    risk_level: str = Field(
        ...,
        description="风险等级：high/medium/low/none",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="风险因素列表（如过宽授权、未使用的子前缀授权等）",
    )
    hijack_surface: list[str] = Field(
        default_factory=list,
        description=(
            "劫持面：过宽授权可能被利用的子前缀范围"
            "（如 192.168.1.0/24 的 maxLength=24 时无劫持面，"
            "maxLength=26 时可被劫持 /25、/26 子前缀）"
        ),
    )
    actual_announcements: list[str] = Field(
        default_factory=list,
        description="实际公告的前缀列表（用于对比）",
    )


# ──────────────────────────────────────────────
# ROA 创建建议
# ──────────────────────────────────────────────


class ROACreationSuggestion(BaseModel):
    """ROA 创建建议。

    遵循 minimal ROA 原则：maxLength 等于实际公告的前缀长度。
    """

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    recommended_max_length: int = Field(
        ..., description="建议的 maxLength（minimal ROA 原则）"
    )
    reason: str = Field(..., description="建议原因")
    minimal_roa: bool = Field(
        True, description="是否为 minimal ROA（maxLength = 前缀长度）"
    )
    importance: str | None = Field(
        None, description="前缀重要度：critical/important/normal/low"
    )
    business_service: str | None = Field(None, description="业务归属")
    customer_id: int | None = Field(None, description="关联客户 ID")


class ROACreationSuggestionResponse(BaseModel):
    """ROA 创建建议响应。"""

    items: list[ROACreationSuggestion] = Field(
        default_factory=list, description="创建建议列表"
    )
    total: int = Field(0, description="建议总数")


# ──────────────────────────────────────────────
# ROA 变更影响评估
# ──────────────────────────────────────────────


class ROAChangeParams(BaseModel):
    """ROA 变更参数。

    用于评估修改 ROA 的 prefix、origin_as、maxLength 或撤销 ROA 的影响。
    所有字段可选，仅评估提供的字段对应的变更。
    """

    new_prefix: str | None = Field(None, description="新前缀（修改前缀时提供）")
    new_origin_as: int | None = Field(
        None, description="新起源 AS（修改 origin AS 时提供）"
    )
    new_max_length: int | None = Field(
        None, description="新 maxLength（修改 maxLength 时提供）"
    )
    revoke: bool = Field(
        False, description="是否评估撤销 ROA 的影响"
    )


class ROAValidationChange(BaseModel):
    """ROA 变更导致的 BGP 公告验证状态变化。"""

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    before_status: str = Field(..., description="变更前验证状态")
    after_status: str = Field(..., description="变更后验证状态")
    before_reason: str | None = Field(None, description="变更前 Invalid 原因")
    after_reason: str | None = Field(None, description="变更后 Invalid 原因")


class ROAChangeImpact(BaseModel):
    """ROA 变更影响评估结果。"""

    roa_id: int = Field(..., description="ROA ID")
    change_params: ROAChangeParams = Field(..., description="变更参数")
    affected_announcements: list[BGPAnnouncementResponse] = Field(
        default_factory=list, description="受影响的 BGP 公告列表"
    )
    affected_business: list[str] = Field(
        default_factory=list, description="受影响的业务服务列表"
    )
    affected_customers: list[int] = Field(
        default_factory=list, description="受影响的客户 ID 列表"
    )
    validation_changes: list[ROAValidationChange] = Field(
        default_factory=list, description="BGP 公告验证状态变化列表"
    )
    is_high_risk: bool = Field(
        False, description="是否为高风险变更（核心前缀变 Invalid 等）"
    )
    risk_description: str = Field(
        "", description="风险描述（如为高风险变更）"
    )


# ──────────────────────────────────────────────
# ROA 覆盖率统计
# ──────────────────────────────────────────────


class ROACoverageByImportance(BaseModel):
    """按重要度分级的 ROA 覆盖率统计。"""

    importance: str = Field(..., description="重要度：critical/important/normal/low")
    total_prefixes: int = Field(0, description="该重要度的前缀总数")
    covered_prefixes: int = Field(0, description="已覆盖 ROA 的前缀数")
    coverage_rate: float = Field(0.0, description="覆盖率（0-1）")


class ROACoverageByStatus(BaseModel):
    """按 RPKI 验证状态分组的统计。"""

    validation_status: str = Field(
        ..., description="验证状态：valid/invalid/not_found"
    )
    count: int = Field(0, description="该状态下的公告数")


class ROACoverageStats(BaseModel):
    """ROA 覆盖率统计。"""

    total_prefixes: int = Field(0, description="总前缀数（已登记）")
    covered_prefixes: int = Field(0, description="有 ROA 覆盖的前缀数")
    coverage_rate: float = Field(0.0, description="总覆盖率（0-1）")
    total_announcements: int = Field(0, description="BGP 公告总数")
    by_importance: list[ROACoverageByImportance] = Field(
        default_factory=list, description="按重要度分级的覆盖率统计"
    )
    by_status: list[ROACoverageByStatus] = Field(
        default_factory=list, description="按验证状态分组的公告统计"
    )


# ──────────────────────────────────────────────
# ROA 健康度摘要
# ──────────────────────────────────────────────


class ROAHealthSummary(BaseModel):
    """ROA 健康度摘要。"""

    total_roas: int = Field(0, description="ROA 总数")
    valid_roas: int = Field(0, description="有效 ROA 数")
    expired_roas: int = Field(0, description="过期 ROA 数")
    revoked_roas: int = Field(0, description="已撤销 ROA 数")
    coverage_rate: float = Field(0.0, description="ROA 覆盖率（0-1）")
    missing_count: int = Field(0, description="缺失 ROA 的前缀数")
    conflict_count: int = Field(0, description="ROA 冲突数")
    high_risk_count: int = Field(0, description="高风险 ROA 数（maxLength 过宽）")
    overall_healthy: bool = Field(
        True, description="整体是否健康（无过期、无冲突、覆盖率达标）"
    )
    summary: dict[str, Any] = Field(
        default_factory=dict, description="附加摘要信息"
    )


__all__ = [
    "MaxLengthRiskResult",
    "ROAChangeImpact",
    "ROAChangeParams",
    "ROAConflictCheckResponse",
    "ROAConflictCheckResult",
    "ROACoverageByImportance",
    "ROACoverageByStatus",
    "ROACoverageStats",
    "ROACreationSuggestion",
    "ROACreationSuggestionResponse",
    "ROADetailResponse",
    "ROAHealthSummary",
    "ROAListResponse",
    "ROAMissingCheckResponse",
    "ROAMissingCheckResult",
    "ROAQueryParams",
    "ROAValidationChange",
]
