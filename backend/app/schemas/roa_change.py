"""ROA 变更审批相关 Pydantic 模式（请求与响应）。

包含 ROA 变更请求、审批动作、审批规则等模式。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# ROA 变更请求
# ──────────────────────────────────────────────


class ROAChangeRequestCreate(BaseModel):
    """创建 ROA 变更请求。"""

    change_type: str = Field(
        ...,
        description="变更类型：create/modify/revoke",
    )
    roa_id: int | None = Field(
        None, description="关联的 ROA ID（修改/撤销时必填）"
    )
    prefix: str | None = Field(
        None, description="变更后的前缀（create/modify 时填写）"
    )
    origin_as: int | None = Field(
        None, description="变更后的起源 AS 号（create/modify 时填写）"
    )
    max_length: int | None = Field(
        None, description="变更后的最大前缀长度（create/modify 时填写）"
    )
    reason: str = Field(..., description="变更原因")


class ROAChangeRequestUpdate(BaseModel):
    """更新 ROA 变更请求（仅支持更新状态与审批意见）。"""

    status: str | None = Field(None, description="变更请求状态")
    approval_comments: str | None = Field(None, description="审批意见")


class UserInfo(BaseModel):
    """用户简要信息（用于变更请求响应中嵌入申请人/审批人信息）。"""

    id: int
    username: str
    full_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ROAChangeRequestResponse(BaseModel):
    """ROA 变更请求响应（完整字段）。"""

    id: int
    change_type: str
    roa_id: int | None
    prefix: str | None
    origin_as: int | None
    max_length: int | None
    current_prefix: str | None
    current_origin_as: int | None
    current_max_length: int | None
    reason: str
    impact_summary: dict[str, Any] | None
    risk_level: str
    status: str
    approval_rule_id: int | None
    required_approvals: int
    approvals: list[dict[str, Any]] | None
    requested_by: int
    approved_by: int | None
    approval_comments: str | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None
    rollback_info: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    tenant_id: int | None

    # 嵌入的用户信息
    requester: UserInfo | None = Field(
        None, description="申请人信息"
    )
    approver: UserInfo | None = Field(
        None, description="审批人信息"
    )

    model_config = ConfigDict(from_attributes=True)


class ROAChangeRequestListResponse(BaseModel):
    """ROA 变更请求分页列表响应。"""

    items: list[ROAChangeRequestResponse] = Field(
        default_factory=list, description="变更请求列表"
    )
    total: int = Field(0, description="总记录数")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(50, description="返回记录数上限")


# ──────────────────────────────────────────────
# 审批动作
# ──────────────────────────────────────────────


class ROAApprovalAction(BaseModel):
    """审批动作请求。"""

    action: str = Field(
        ..., description="审批动作：approve/reject"
    )
    comments: str | None = Field(None, description="审批意见")


# ──────────────────────────────────────────────
# 变更执行结果
# ──────────────────────────────────────────────


class ROAChangeExecutionResult(BaseModel):
    """ROA 变更执行结果。"""

    success: bool = Field(..., description="是否执行成功")
    message: str = Field(..., description="执行结果消息")
    roa_id: int | None = Field(None, description="受影响的 ROA ID")
    validation_status: str | None = Field(
        None, description="变更后验证状态"
    )
    error: str | None = Field(None, description="错误信息（失败时）")


# ──────────────────────────────────────────────
# 变更后验证结果
# ──────────────────────────────────────────────


class ROAChangeVerificationResult(BaseModel):
    """ROA 变更后验证结果。"""

    request_id: int = Field(..., description="变更请求 ID")
    roa_id: int | None = Field(None, description="关联的 ROA ID")
    roa_status: str | None = Field(
        None, description="ROA 当前状态"
    )
    vrp_updated: bool = Field(
        ..., description="VRP 是否已更新"
    )
    vrp_count: int = Field(0, description="关联 VRP 数量")
    bgp_validation_passed: bool = Field(
        ..., description="BGP 验证是否通过"
    )
    affected_announcements: int = Field(
        0, description="受影响的 BGP 公告数"
    )
    validation_details: dict[str, Any] = Field(
        default_factory=dict, description="验证详情"
    )
    issues: list[str] = Field(
        default_factory=list, description="发现的问题列表"
    )


# ──────────────────────────────────────────────
# 审批规则
# ──────────────────────────────────────────────


class ROAApprovalRuleCreate(BaseModel):
    """创建审批规则。"""

    name: str = Field(..., description="规则名称")
    description: str | None = Field(None, description="规则描述")
    rule_type: str = Field(
        ...,
        description=(
            "审批类型：auto_approve/single_approval/"
            "dual_approval/committee"
        ),
    )
    conditions: dict[str, Any] | None = Field(
        None,
        description=(
            "触发条件（JSON），如 "
            '{"change_type": ["revoke"], "prefix_importance": ["critical"]}'
        ),
    )
    approvers: list[int] | None = Field(
        None, description="审批人 ID 列表"
    )
    enabled: bool = Field(True, description="是否启用")
    priority: int = Field(100, description="优先级（数值越小越高）")


class ROAApprovalRuleUpdate(BaseModel):
    """更新审批规则。"""

    name: str | None = Field(None, description="规则名称")
    description: str | None = Field(None, description="规则描述")
    rule_type: str | None = Field(None, description="审批类型")
    conditions: dict[str, Any] | None = Field(
        None, description="触发条件"
    )
    approvers: list[int] | None = Field(
        None, description="审批人 ID 列表"
    )
    enabled: bool | None = Field(None, description="是否启用")
    priority: int | None = Field(None, description="优先级")


class ROAApprovalRuleResponse(BaseModel):
    """审批规则响应。"""

    id: int
    name: str
    description: str | None
    rule_type: str
    conditions: dict[str, Any] | None
    approvers: list[int] | None
    enabled: bool
    priority: int
    created_at: datetime
    updated_at: datetime
    tenant_id: int | None

    model_config = ConfigDict(from_attributes=True)


class ROAApprovalRuleListResponse(BaseModel):
    """审批规则列表响应。"""

    items: list[ROAApprovalRuleResponse] = Field(
        default_factory=list, description="审批规则列表"
    )
    total: int = Field(0, description="总记录数")


# ──────────────────────────────────────────────
# 审批流程匹配结果
# ──────────────────────────────────────────────


class ApprovalFlowMatch(BaseModel):
    """审批流程匹配结果。"""

    rule_id: int | None = Field(
        None, description="匹配的审批规则 ID（无匹配时为 None）"
    )
    rule_name: str | None = Field(None, description="匹配的规则名称")
    rule_type: str = Field(
        ..., description="审批类型"
    )
    required_approvals: int = Field(
        ..., description="所需审批人数"
    )
    approvers: list[int] = Field(
        default_factory=list, description="审批人 ID 列表"
    )
    is_high_risk: bool = Field(
        False, description="是否为高风险变更（强制审批）"
    )
    description: str = Field(
        "", description="匹配说明"
    )


__all__ = [
    "ApprovalFlowMatch",
    "ROAApprovalAction",
    "ROAApprovalRuleCreate",
    "ROAApprovalRuleListResponse",
    "ROAApprovalRuleResponse",
    "ROAApprovalRuleUpdate",
    "ROAChangeExecutionResult",
    "ROAChangeRequestCreate",
    "ROAChangeRequestListResponse",
    "ROAChangeRequestResponse",
    "ROAChangeRequestUpdate",
    "ROAChangeVerificationResult",
    "UserInfo",
]
