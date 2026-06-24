"""ROV（Route Origin Validation）策略模拟与变更影响评估相关 Pydantic 模式。

包含 ROV 策略模拟请求/响应、受影响前缀/业务/客户、部署建议、风险评估，
以及 ROA 变更模拟请求/响应、验证状态变化与攻击面分析等模式。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────
# ROV 策略模拟
# ──────────────────────────────────────────────


class ROVSimulationScope(BaseModel):
    """ROV 模拟范围过滤条件。

    所有字段可选，未提供的字段表示不进行该维度过滤。
    """

    router_ids: list[int] | None = Field(
        None, description="路由器 ID 列表（使用观察点 ID 作为近似）"
    )
    regions: list[str] | None = Field(None, description="地域列表")
    sites: list[str] | None = Field(None, description="机房列表")
    vrfs: list[str] | None = Field(None, description="VRF 列表")
    address_families: list[int] | None = Field(
        None, description="地址族列表（4 表示 IPv4，6 表示 IPv6）"
    )
    business_domains: list[str] | None = Field(
        None, description="业务域列表（对应前缀的 business_service）"
    )
    importance_levels: list[str] | None = Field(
        None, description="前缀重要度列表：critical/important/normal/low"
    )


class ROVSimulationRequest(BaseModel):
    """ROV 策略模拟请求。"""

    policy: str = Field(
        ...,
        description="ROV 策略：drop_invalid（拒收）/de-preference_invalid（降权）/monitor_only（仅监控）",
    )
    scope: ROVSimulationScope = Field(
        default_factory=ROVSimulationScope,
        description="模拟范围过滤条件",
    )
    snapshot_time: datetime | None = Field(
        None, description="快照时间（模拟历史路由表，为空表示当前）"
    )

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, v: str) -> str:
        """校验 ROV 策略取值。"""
        allowed = {"drop_invalid", "de-preference_invalid", "monitor_only"}
        if v not in allowed:
            raise ValueError(f"policy 必须为 {allowed} 之一")
        return v


class AffectedPrefix(BaseModel):
    """受影响的前缀。"""

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    current_status: str = Field(
        ..., description="当前 RPKI 验证状态：valid/invalid/not_found"
    )
    simulated_status: str = Field(
        ...,
        description="模拟后状态：valid/invalid/not_found/rejected/de-preferenced",
    )
    impact_description: str = Field("", description="影响描述")
    importance: str | None = Field(
        None, description="前缀重要度：critical/important/normal/low"
    )


class AffectedBusiness(BaseModel):
    """受影响的业务。"""

    business_service: str = Field(..., description="业务服务名称")
    affected_prefixes: list[str] = Field(
        default_factory=list, description="受影响的前缀列表"
    )
    impact_level: str = Field(
        ..., description="影响等级：high/medium/low"
    )
    description: str = Field("", description="影响描述")


class AffectedCustomer(BaseModel):
    """受影响的客户。"""

    customer_id: int = Field(..., description="客户 ID")
    customer_name: str = Field(..., description="客户名称")
    affected_prefixes: list[str] = Field(
        default_factory=list, description="受影响的前缀列表"
    )
    impact_level: str = Field(
        ..., description="影响等级：high/medium/low"
    )


class DeploymentRecommendation(BaseModel):
    """分阶段部署建议。"""

    phase: str = Field(
        ..., description="部署阶段：monitor（监控）/de-preference（降权）/drop（拒收）"
    )
    description: str = Field(..., description="阶段描述")
    prerequisites: list[str] = Field(
        default_factory=list, description="前置条件列表"
    )
    affected_prefixes: list[str] = Field(
        default_factory=list, description="该阶段受影响的前缀列表"
    )


class RiskAssessment(BaseModel):
    """风险评估。"""

    risk_level: str = Field(
        ..., description="风险等级：high/medium/low/none"
    )
    risk_factors: list[str] = Field(
        default_factory=list, description="风险因素列表"
    )
    blocking_issues: list[str] = Field(
        default_factory=list, description="阻断问题列表（需解决才能继续）"
    )
    requires_approval: bool = Field(
        False, description="是否需要审批后方可实施"
    )


class ROVSimulationResult(BaseModel):
    """ROV 策略模拟结果。"""

    policy: str = Field(..., description="模拟的 ROV 策略")
    total_announcements: int = Field(0, description="范围内的公告总数")
    valid_count: int = Field(0, description="Valid 公告数")
    invalid_count: int = Field(0, description="Invalid 公告数")
    not_found_count: int = Field(0, description="NotFound 公告数")
    affected_prefixes: list[AffectedPrefix] = Field(
        default_factory=list, description="受影响的前缀列表"
    )
    affected_business: list[AffectedBusiness] = Field(
        default_factory=list, description="受影响的业务列表"
    )
    affected_customers: list[AffectedCustomer] = Field(
        default_factory=list, description="受影响的客户列表"
    )
    deployment_recommendations: list[DeploymentRecommendation] = Field(
        default_factory=list, description="分阶段部署建议"
    )
    risk_assessment: RiskAssessment = Field(
        default_factory=RiskAssessment, description="风险评估"
    )


# ──────────────────────────────────────────────
# ROA 变更模拟
# ──────────────────────────────────────────────


class ROAChangeSimulationRequest(BaseModel):
    """ROA 变更模拟请求。"""

    roa_id: int | None = Field(
        None, description="ROA ID（modify/revoke 时必须提供）"
    )
    change_type: str = Field(
        ..., description="变更类型：create（新建）/modify（修改）/revoke（撤销）"
    )
    new_prefix: str | None = Field(None, description="新前缀（create/modify 时提供）")
    new_origin_as: int | None = Field(
        None, description="新起源 AS（create/modify 时提供）"
    )
    new_max_length: int | None = Field(
        None, description="新最大前缀长度（create/modify 时提供）"
    )

    @field_validator("change_type")
    @classmethod
    def validate_change_type(cls, v: str) -> str:
        """校验变更类型取值。"""
        allowed = {"create", "modify", "revoke"}
        if v not in allowed:
            raise ValueError(f"change_type 必须为 {allowed} 之一")
        return v

    @model_validator(mode="after")
    def validate_request(self) -> "ROAChangeSimulationRequest":
        """跨字段校验：根据变更类型检查必填字段。"""
        if self.change_type in ("modify", "revoke") and self.roa_id is None:
            raise ValueError("modify/revoke 变更类型必须提供 roa_id")
        if self.change_type == "create" and (
            self.new_prefix is None or self.new_origin_as is None
        ):
            raise ValueError("create 变更类型必须提供 new_prefix 和 new_origin_as")
        return self


class AffectedAnnouncement(BaseModel):
    """受 ROA 变更影响的 BGP 公告。"""

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    prefix_length: int = Field(..., description="前缀长度")
    address_family: int = Field(4, description="地址族：4 (IPv4) 或 6 (IPv6)")
    current_validation_status: str = Field(
        ..., description="当前 RPKI 验证状态：valid/invalid/not_found"
    )
    rpki_invalid_reason: str | None = Field(
        None, description="当前 RPKI 验证失败原因（如为 Invalid）"
    )
    importance: str | None = Field(
        None, description="前缀重要度：critical/important/normal/low"
    )
    business_service: str | None = Field(
        None, description="所属业务服务名称"
    )


class ValidationChange(BaseModel):
    """ROA 变更导致的 BGP 公告验证状态变化。"""

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    old_status: str = Field(..., description="变更前验证状态")
    new_status: str = Field(..., description="变更后验证状态")
    change_reason: str = Field("", description="状态变化原因")


class AttackSurfaceItem(BaseModel):
    """新增攻击面条目。"""

    prefix: str = Field(..., description="网络前缀")
    origin_as: int | None = Field(None, description="起源 AS 号")
    description: str = Field("", description="攻击面描述")
    risk_level: str = Field(..., description="风险等级：high/medium/low")
    attack_type: str = Field(
        "",
        description=(
            "攻击面类型：sub_prefix_hijack（子前缀劫持）/"
            "unauthorized_origin（未授权 origin）/"
            "over_authorization（过宽授权）/"
            "coverage_expansion（覆盖范围扩大）"
        ),
    )
    affected_subprefixes: list[str] = Field(
        default_factory=list, description="受影响的子前缀列表（如适用）"
    )


class ROAChangeSimulationResult(BaseModel):
    """ROA 变更模拟结果。"""

    validation_changes: list[ValidationChange] = Field(
        default_factory=list, description="验证状态变化列表"
    )
    affected_announcements: list[AffectedAnnouncement] = Field(
        default_factory=list, description="受影响 BGP 公告清单"
    )
    new_attack_surface: list[AttackSurfaceItem] = Field(
        default_factory=list, description="新增攻击面列表"
    )
    risk_assessment: RiskAssessment = Field(
        default_factory=RiskAssessment, description="风险评估"
    )


# ──────────────────────────────────────────────
# 细粒度 ROA 变更模拟请求（按变更类型拆分）
# ──────────────────────────────────────────────


class ROACreationSimulationRequest(BaseModel):
    """ROA 创建模拟请求。"""

    prefix: str = Field(..., description="新 ROA 的网络前缀（含前缀长度）")
    origin_as: int = Field(..., description="新 ROA 授权的起源 AS 号")
    max_length: int | None = Field(
        None,
        description=(
            "新 ROA 的最大前缀长度，为空时采用 minimal ROA 原则"
            "（等于前缀长度）"
        ),
    )


class ROAModificationSimulationRequest(BaseModel):
    """ROA 修改模拟请求。

    任意字段为 None 时表示保持原值不变。
    """

    roa_id: int = Field(..., description="待修改的 ROA ID")
    new_prefix: str | None = Field(None, description="新前缀（如变更前缀）")
    new_origin_as: int | None = Field(
        None, description="新起源 AS（如变更 origin）"
    )
    new_max_length: int | None = Field(
        None, description="新最大前缀长度（如调整 maxLength）"
    )


class ROARevocationSimulationRequest(BaseModel):
    """ROA 撤销模拟请求。"""

    roa_id: int = Field(..., description="待撤销的 ROA ID")


# ──────────────────────────────────────────────
# 导出
# ──────────────────────────────────────────────


class ROVExportRequest(BaseModel):
    """ROV 模拟结果导出请求。"""

    simulation_request: ROVSimulationRequest = Field(
        ..., description="模拟请求参数"
    )
    format: str = Field("json", description="导出格式：json/csv")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """校验导出格式取值。"""
        allowed = {"json", "csv"}
        if v not in allowed:
            raise ValueError(f"format 必须为 {allowed} 之一")
        return v


class ROVExportResponse(BaseModel):
    """ROV 模拟结果导出响应。"""

    format: str = Field(..., description="导出格式")
    content: str = Field(..., description="导出内容（JSON 字符串或 CSV 文本）")
    filename: str = Field(..., description="建议的文件名")


__all__ = [
    "AffectedAnnouncement",
    "AffectedBusiness",
    "AffectedCustomer",
    "AffectedPrefix",
    "AttackSurfaceItem",
    "DeploymentRecommendation",
    "ROAChangeSimulationRequest",
    "ROAChangeSimulationResult",
    "ROACreationSimulationRequest",
    "ROAModificationSimulationRequest",
    "ROARevocationSimulationRequest",
    "ROVExportRequest",
    "ROVExportResponse",
    "ROVSimulationRequest",
    "ROVSimulationResult",
    "ROVSimulationScope",
    "RiskAssessment",
    "ValidationChange",
]
