"""自动取证与处置闭环相关 Pydantic 模式（请求与响应）。

包含取证证据、处置动作、事件复盘、通知渠道、通知记录与案例库的 CRUD 模式，
以及取证采集、处置建议生成与通知发送的结果模式。

注意：
    本模块不通过 ``app.schemas.__init__`` 注册（共享文件不可修改），
    使用方需直接 ``from app.schemas.forensics import ...`` 显式导入。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ──────────────────────────────────────────────
# 枚举集合
# ──────────────────────────────────────────────


# 证据类型
EVIDENCE_TYPES = {
    "roa_vrp",
    "bgp_sample",
    "as_path",
    "propagation_scope",
    "observation_point",
    "asset_relation",
    "change_record",
    "historical_baseline",
    "other",
}

# 处置动作类型
REMEDIATION_ACTION_TYPES = {
    "contact_asn",
    "contact_upstream",
    "fix_roa",
    "adjust_policy",
    "announce_legitimate_prefix",
    "scrubber_coordination",
    "customer_notification",
    "other",
}

# 处置动作状态
REMEDIATION_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "failed",
    "skipped",
}

# 处置动作优先级
REMEDIATION_PRIORITIES = {"immediate", "high", "medium", "low"}

# 通知渠道类型
CHANNEL_TYPES = {
    "webhook",
    "email",
    "sms",
    "wechat_work",
    "dingtalk",
    "slack",
    "teams",
    "pagerduty",
    "itsm",
    "soc",
    "other",
}

# 通知状态
NOTIFICATION_STATUSES = {"pending", "sent", "failed", "retry"}

# 严重等级
SEVERITY_LEVELS = {"P0", "P1", "P2", "P3", "P4"}


# ──────────────────────────────────────────────
# 取证证据
# ──────────────────────────────────────────────


class ForensicEvidenceBase(BaseModel):
    """取证证据基础字段。"""

    incident_id: int | None = Field(None, description="关联事件 ID")
    alert_id: int | None = Field(None, description="关联告警 ID")
    evidence_type: str = Field(..., description="证据类型")
    title: str = Field(..., max_length=500, description="证据标题")
    description: str | None = Field(None, description="证据描述")
    content: dict[str, Any] | None = Field(None, description="证据内容快照")
    source: str | None = Field(None, max_length=255, description="证据来源")
    collected_at: datetime = Field(..., description="证据采集时间")
    collected_by: int | None = Field(None, description="采集人用户 ID")
    is_auto_collected: bool = Field(default=True, description="是否为自动采集")
    integrity_hash: str | None = Field(None, max_length=128, description="证据完整性哈希")

    @field_validator("evidence_type")
    @classmethod
    def validate_evidence_type(cls, v: str) -> str:
        """校验证据类型。"""
        if v not in EVIDENCE_TYPES:
            raise ValueError(f"evidence_type 必须为 {EVIDENCE_TYPES} 之一")
        return v


class ForensicEvidenceCreate(ForensicEvidenceBase):
    """创建取证证据请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class ForensicEvidenceUpdate(BaseModel):
    """更新取证证据请求。"""

    title: str | None = Field(None, max_length=500, description="证据标题")
    description: str | None = Field(None, description="证据描述")
    content: dict[str, Any] | None = Field(None, description="证据内容快照")
    integrity_hash: str | None = Field(None, max_length=128, description="证据完整性哈希")


class ForensicEvidenceResponse(ForensicEvidenceBase):
    """取证证据响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ForensicEvidenceListResponse(BaseModel):
    """取证证据列表响应（带分页信息）。"""

    items: list[ForensicEvidenceResponse]
    total: int
    skip: int
    limit: int


class ForensicEvidenceQueryParams(BaseModel):
    """取证证据查询参数。"""

    incident_id: int | None = Field(None, description="按事件 ID 过滤")
    alert_id: int | None = Field(None, description="按告警 ID 过滤")
    evidence_type: str | None = Field(None, description="按证据类型过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


class ForensicCollectionRequest(BaseModel):
    """自动取证采集请求。

    支持两种输入：
    1. 提供 ``incident_id``：采集指定事件的全部证据
    2. 提供 ``alert_id``：采集指定告警的证据
    """

    incident_id: int | None = Field(None, description="事件 ID")
    alert_id: int | None = Field(None, description="告警 ID")
    evidence_types: list[str] | None = Field(
        None, description="指定采集的证据类型（为空则全部采集）"
    )

    @model_validator(mode="after")
    def validate_input(self) -> ForensicCollectionRequest:
        """校验输入：必须提供 incident_id 或 alert_id。"""
        if self.incident_id is None and self.alert_id is None:
            raise ValueError("必须提供 incident_id 或 alert_id")
        return self


class ForensicCollectionResult(BaseModel):
    """自动取证采集结果。"""

    incident_id: int | None = Field(None, description="关联事件 ID")
    alert_id: int | None = Field(None, description="关联告警 ID")
    collected_count: int = Field(0, description="采集证据数量")
    evidence_ids: list[int] = Field(default_factory=list, description="采集的证据 ID 列表")
    evidence_by_type: dict[str, int] = Field(
        default_factory=dict, description="按证据类型分组的数量"
    )
    errors: list[str] = Field(default_factory=list, description="采集错误列表")


# ──────────────────────────────────────────────
# 处置动作
# ──────────────────────────────────────────────


class RemediationActionBase(BaseModel):
    """处置动作基础字段。"""

    incident_id: int | None = Field(None, description="关联事件 ID")
    action_type: str = Field(..., description="动作类型")
    title: str = Field(..., max_length=500, description="动作标题")
    description: str | None = Field(None, description="动作描述")
    target: str | None = Field(None, max_length=255, description="处置目标")
    priority: str = Field(default="medium", description="优先级：immediate/high/medium/low")
    status: str = Field(
        default="pending", description="状态：pending/in_progress/completed/failed/skipped"
    )
    is_auto_generated: bool = Field(default=False, description="是否为自动生成的建议动作")

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        """校验动作类型。"""
        if v not in REMEDIATION_ACTION_TYPES:
            raise ValueError(f"action_type 必须为 {REMEDIATION_ACTION_TYPES} 之一")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """校验优先级。"""
        if v not in REMEDIATION_PRIORITIES:
            raise ValueError(f"priority 必须为 {REMEDIATION_PRIORITIES} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        if v not in REMEDIATION_STATUSES:
            raise ValueError(f"status 必须为 {REMEDIATION_STATUSES} 之一")
        return v


class RemediationActionCreate(RemediationActionBase):
    """创建处置动作请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class RemediationActionUpdate(BaseModel):
    """更新处置动作请求。"""

    title: str | None = Field(None, max_length=500, description="动作标题")
    description: str | None = Field(None, description="动作描述")
    target: str | None = Field(None, max_length=255, description="处置目标")
    priority: str | None = Field(None, description="优先级")
    status: str | None = Field(None, description="状态")
    result: str | None = Field(None, description="执行结果")
    result_details: dict[str, Any] | None = Field(None, description="执行结果详情")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        """校验优先级。"""
        if v is None:
            return v
        if v not in REMEDIATION_PRIORITIES:
            raise ValueError(f"priority 必须为 {REMEDIATION_PRIORITIES} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态。"""
        if v is None:
            return v
        if v not in REMEDIATION_STATUSES:
            raise ValueError(f"status 必须为 {REMEDIATION_STATUSES} 之一")
        return v


class RemediationActionResponse(RemediationActionBase):
    """处置动作响应。"""

    id: int
    executed_by: int | None
    executed_at: datetime | None
    result: str | None
    result_details: dict[str, Any] | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RemediationActionListResponse(BaseModel):
    """处置动作列表响应（带分页信息）。"""

    items: list[RemediationActionResponse]
    total: int
    skip: int
    limit: int


class RemediationActionQueryParams(BaseModel):
    """处置动作查询参数。"""

    incident_id: int | None = Field(None, description="按事件 ID 过滤")
    action_type: str | None = Field(None, description="按动作类型过滤")
    status: str | None = Field(None, description="按状态过滤")
    priority: str | None = Field(None, description="按优先级过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


class RemediationSuggestionRequest(BaseModel):
    """处置建议生成请求。"""

    incident_id: int = Field(..., description="事件 ID")


class RemediationSuggestionResult(BaseModel):
    """处置建议生成结果。"""

    incident_id: int = Field(..., description="事件 ID")
    suggestions: list[RemediationActionResponse] = Field(
        default_factory=list, description="生成的建议动作列表"
    )
    summary: str = Field(default="", description="处置建议总结")


class RemediationExecuteRequest(BaseModel):
    """处置动作执行请求。"""

    action_id: int = Field(..., description="处置动作 ID")
    result: str | None = Field(None, description="执行结果")
    result_details: dict[str, Any] | None = Field(None, description="执行结果详情")
    status: str = Field(default="completed", description="执行后状态：completed/failed/skipped")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态。"""
        allowed = {"completed", "failed", "skipped"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


# ──────────────────────────────────────────────
# 事件复盘
# ──────────────────────────────────────────────


class IncidentReviewBase(BaseModel):
    """事件复盘基础字段。"""

    incident_id: int = Field(..., description="关联事件 ID")
    root_cause: str = Field(..., description="根因分析")
    lessons_learned: str | None = Field(None, description="经验教训")
    improvements: str | None = Field(None, description="改进措施")
    prevention_measures: str | None = Field(None, description="预防措施")
    review_summary: str | None = Field(None, description="复盘总结")
    reviewed_by: int | None = Field(None, description="复盘人用户 ID")
    reviewed_at: datetime = Field(..., description="复盘时间")
    evidence_preserved: bool = Field(default=True, description="是否已保留证据与操作链")
    operation_chain: list[dict[str, Any]] | None = Field(
        None, description="操作链（处置动作时间线）"
    )
    rule_updates: list[dict[str, Any]] | None = Field(None, description="沉淀的规则更新建议")


class IncidentReviewCreate(IncidentReviewBase):
    """创建事件复盘请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class IncidentReviewUpdate(BaseModel):
    """更新事件复盘请求。"""

    root_cause: str | None = Field(None, description="根因分析")
    lessons_learned: str | None = Field(None, description="经验教训")
    improvements: str | None = Field(None, description="改进措施")
    prevention_measures: str | None = Field(None, description="预防措施")
    review_summary: str | None = Field(None, description="复盘总结")
    evidence_preserved: bool | None = Field(None, description="是否已保留证据与操作链")
    operation_chain: list[dict[str, Any]] | None = Field(None, description="操作链")
    rule_updates: list[dict[str, Any]] | None = Field(None, description="沉淀的规则更新建议")


class IncidentReviewResponse(IncidentReviewBase):
    """事件复盘响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentReviewListResponse(BaseModel):
    """事件复盘列表响应（带分页信息）。"""

    items: list[IncidentReviewResponse]
    total: int
    skip: int
    limit: int


class IncidentCloseAndReviewRequest(BaseModel):
    """事件关闭与复盘请求。

    用于一次性完成事件关闭、复盘记录创建与证据保留。
    """

    incident_id: int = Field(..., description="事件 ID")
    resolution: str = Field(..., description="处置结论")
    root_cause: str = Field(..., description="根因分析")
    lessons_learned: str | None = Field(None, description="经验教训")
    improvements: str | None = Field(None, description="改进措施")
    prevention_measures: str | None = Field(None, description="预防措施")
    preserve_evidence: bool = Field(default=True, description="是否保留证据与操作链")
    save_to_case_library: bool = Field(default=False, description="是否沉淀到案例库")
    case_title: str | None = Field(
        None, max_length=500, description="案例标题（沉淀到案例库时使用）"
    )
    case_tags: list[str] | None = Field(None, description="案例标签（沉淀到案例库时使用）")


# ──────────────────────────────────────────────
# 通知渠道
# ──────────────────────────────────────────────


class NotificationChannelBase(BaseModel):
    """通知渠道基础字段。"""

    name: str = Field(..., min_length=1, max_length=255, description="渠道名称")
    channel_type: str = Field(..., description="渠道类型")
    config: dict[str, Any] | None = Field(None, description="渠道配置")
    enabled: bool = Field(default=True, description="是否启用")
    description: str | None = Field(None, description="渠道描述")
    severity_filter: list[str] | None = Field(None, description="严重等级过滤")
    event_filter: list[str] | None = Field(None, description="事件类型过滤")

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        """校验渠道类型。"""
        if v not in CHANNEL_TYPES:
            raise ValueError(f"channel_type 必须为 {CHANNEL_TYPES} 之一")
        return v


class NotificationChannelCreate(NotificationChannelBase):
    """创建通知渠道请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class NotificationChannelUpdate(BaseModel):
    """更新通知渠道请求。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="渠道名称")
    config: dict[str, Any] | None = Field(None, description="渠道配置")
    enabled: bool | None = Field(None, description="是否启用")
    description: str | None = Field(None, description="渠道描述")
    severity_filter: list[str] | None = Field(None, description="严重等级过滤")
    event_filter: list[str] | None = Field(None, description="事件类型过滤")


class NotificationChannelResponse(NotificationChannelBase):
    """通知渠道响应。"""

    id: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationChannelListResponse(BaseModel):
    """通知渠道列表响应（带分页信息）。"""

    items: list[NotificationChannelResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# 通知记录
# ──────────────────────────────────────────────


class NotificationLogResponse(BaseModel):
    """通知记录响应。"""

    id: int
    incident_id: int | None
    channel_id: int | None
    channel_type: str
    title: str
    content: str | None
    content_details: dict[str, Any] | None
    status: str
    error_message: str | None
    sent_at: datetime | None
    retry_count: int
    triggered_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationLogListResponse(BaseModel):
    """通知记录列表响应（带分页信息）。"""

    items: list[NotificationLogResponse]
    total: int
    skip: int
    limit: int


class NotificationSendRequest(BaseModel):
    """通知发送请求。

    支持两种模式：
    1. 指定 ``channel_ids``：通过指定渠道发送
    2. 不指定 ``channel_ids``：通过所有启用的渠道发送
    """

    incident_id: int = Field(..., description="事件 ID")
    channel_ids: list[int] | None = Field(
        None, description="指定通知渠道 ID 列表（为空则通知所有启用渠道）"
    )
    title: str | None = Field(None, max_length=500, description="通知标题")
    content: str | None = Field(None, description="通知内容")
    extra_details: dict[str, Any] | None = Field(
        None, description="附加详情（合并到 content_details）"
    )


class NotificationSendResult(BaseModel):
    """通知发送结果。"""

    incident_id: int = Field(..., description="事件 ID")
    total_channels: int = Field(0, description="通知渠道总数")
    sent_count: int = Field(0, description="成功发送数")
    failed_count: int = Field(0, description="失败数")
    log_ids: list[int] = Field(default_factory=list, description="通知记录 ID 列表")
    errors: list[str] = Field(default_factory=list, description="发送错误列表")


# ──────────────────────────────────────────────
# 案例库
# ──────────────────────────────────────────────


class CaseLibraryBase(BaseModel):
    """案例库基础字段。"""

    title: str = Field(..., min_length=1, max_length=500, description="案例标题")
    description: str | None = Field(None, description="案例描述")
    root_cause: str | None = Field(None, description="根因分析")
    remediation_plan: str | None = Field(None, description="处置方案")
    tags: list[str] | None = Field(None, description="标签列表")
    severity: str = Field(default="P3", description="严重等级")
    incident_ids: list[int] | None = Field(None, description="关联事件 ID 列表")
    alert_type: str | None = Field(None, description="关联告警类型")
    affected_prefixes: list[str] | None = Field(None, description="受影响前缀列表")
    affected_asns: list[int] | None = Field(None, description="受影响 ASN 列表")
    is_published: bool = Field(default=False, description="是否已发布")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """校验严重等级。"""
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"severity 必须为 {SEVERITY_LEVELS} 之一")
        return v


class CaseLibraryCreate(CaseLibraryBase):
    """创建案例请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")
    created_by: int | None = Field(None, description="创建人用户 ID")


class CaseLibraryUpdate(BaseModel):
    """更新案例请求。"""

    title: str | None = Field(None, min_length=1, max_length=500, description="案例标题")
    description: str | None = Field(None, description="案例描述")
    root_cause: str | None = Field(None, description="根因分析")
    remediation_plan: str | None = Field(None, description="处置方案")
    tags: list[str] | None = Field(None, description="标签列表")
    severity: str | None = Field(None, description="严重等级")
    incident_ids: list[int] | None = Field(None, description="关联事件 ID 列表")
    alert_type: str | None = Field(None, description="关联告警类型")
    affected_prefixes: list[str] | None = Field(None, description="受影响前缀列表")
    affected_asns: list[int] | None = Field(None, description="受影响 ASN 列表")
    is_published: bool | None = Field(None, description="是否已发布")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        """校验严重等级。"""
        if v is None:
            return v
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"severity 必须为 {SEVERITY_LEVELS} 之一")
        return v


class CaseLibraryResponse(CaseLibraryBase):
    """案例响应。"""

    id: int
    created_by: int | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseLibraryListResponse(BaseModel):
    """案例列表响应（带分页信息）。"""

    items: list[CaseLibraryResponse]
    total: int
    skip: int
    limit: int


class CaseLibraryQueryParams(BaseModel):
    """案例查询参数。"""

    severity: str | None = Field(None, description="按严重等级过滤")
    alert_type: str | None = Field(None, description="按告警类型过滤")
    tag: str | None = Field(None, description="按标签过滤")
    is_published: bool | None = Field(None, description="按发布状态过滤")
    keyword: str | None = Field(None, description="关键词搜索（标题与描述）")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


# ──────────────────────────────────────────────
# Task 20 简化接口模式
# ──────────────────────────────────────────────


class EvidenceCollection(BaseModel):
    """自动取证结果。

    描述一次自动取证采集的汇总结果，包含事件 ID、采集时间、
    各类证据数量与证据内容快照。
    """

    incident_id: int = Field(..., description="事件 ID")
    collected_at: datetime = Field(..., description="采集时间")
    collected_by: int | None = Field(None, description="采集人用户 ID")
    evidence_count: int = Field(0, description="证据条目总数")
    evidence_by_type: dict[str, int] = Field(
        default_factory=dict, description="按证据类型分组的数量"
    )
    roa_vrp: list[dict[str, Any]] = Field(default_factory=list, description="ROA/VRP 授权快照")
    bgp_samples: list[dict[str, Any]] = Field(default_factory=list, description="BGP 公告样本")
    as_paths: list[dict[str, Any]] = Field(default_factory=list, description="AS_PATH 路径样本")
    propagation_scope: dict[str, Any] = Field(
        default_factory=dict, description="传播范围（观察点分布）"
    )
    observation_points: list[dict[str, Any]] = Field(default_factory=list, description="观察点信息")
    asset_relations: list[dict[str, Any]] = Field(
        default_factory=list, description="资产关系（前缀/ASN/客户/业务）"
    )
    change_records: list[dict[str, Any]] = Field(default_factory=list, description="变更记录")
    historical_baseline: list[dict[str, Any]] = Field(default_factory=list, description="历史基线")
    errors: list[str] = Field(default_factory=list, description="采集错误列表")


class RemediationSuggestion(BaseModel):
    """处置建议。

    一条处置建议描述针对事件的具体处置步骤，包含类型、优先级、
    描述、可执行步骤与预期影响。
    """

    type: str = Field(
        ...,
        description=(
            "建议类型：contact_asn/fix_roa/adjust_policy/announce_specific/scrubber/notify_customer"
        ),
    )
    priority: str = Field(
        default="medium",
        description="优先级：immediate/high/medium/low",
    )
    description: str = Field(..., description="建议描述")
    actionable_steps: list[str] = Field(default_factory=list, description="可执行步骤列表")
    estimated_impact: str = Field(default="", description="预期影响评估")


class RemediationSuggestionList(BaseModel):
    """处置建议列表响应。"""

    incident_id: int = Field(..., description="事件 ID")
    suggestions: list[RemediationSuggestion] = Field(
        default_factory=list, description="处置建议列表"
    )
    total: int = Field(0, description="建议总数")


class IncidentCloseRequest(BaseModel):
    """事件关闭请求（含复盘信息）。"""

    root_cause: str = Field(..., description="根因分析")
    resolution: str = Field(..., description="处置结论")
    reviewer_id: int = Field(..., description="复盘人用户 ID")
    lessons_learned: str | None = Field(None, description="经验教训")
    improvements: str | None = Field(None, description="改进措施")
    save_to_case_library: bool = Field(default=False, description="是否沉淀到案例库")


class IncidentReview(BaseModel):
    """事件复盘结果。"""

    incident_id: int = Field(..., description="事件 ID")
    root_cause: str = Field(..., description="根因分析")
    resolution: str = Field(..., description="处置结论")
    reviewer_id: int | None = Field(None, description="复盘人用户 ID")
    reviewed_at: datetime = Field(..., description="复盘时间")
    evidence_preserved: bool = Field(default=True, description="是否已保留证据与操作链")
    operation_chain: list[dict[str, Any]] = Field(
        default_factory=list, description="操作链（处置动作时间线）"
    )
    rule_updates: list[dict[str, Any]] = Field(
        default_factory=list, description="沉淀的规则更新建议"
    )
    case_id: int | None = Field(None, description="沉淀的案例 ID（如有）")
    status: str = Field(default="closed", description="事件最终状态")


class NotificationChannelConfig(BaseModel):
    """通知渠道配置。

    描述一个通知渠道的配置信息，用于通知发送时指定渠道参数。
    """

    channel_type: str = Field(
        ...,
        description=("渠道类型：webhook/email/sms/wechat_work/dingtalk/slack/teams/itsm/soc"),
    )
    target: str | None = Field(None, description="投递目标（URL/邮箱列表/手机号/频道等）")
    config: dict[str, Any] = Field(default_factory=dict, description="渠道额外配置")


class NotificationRequest(BaseModel):
    """通知请求。

    用于触发事件通知，支持指定渠道列表与自定义内容。
    """

    incident_id: int = Field(..., description="事件 ID")
    channels: list[str] = Field(
        default_factory=list,
        description=(
            "通知渠道列表：webhook/email/sms/wechat_work/dingtalk/"
            "slack/teams/itsm/soc（为空则按配置发送）"
        ),
    )
    title: str | None = Field(None, description="通知标题")
    content: str | None = Field(None, description="通知内容")
    channel_configs: list[NotificationChannelConfig] | None = Field(
        None, description="自定义渠道配置列表"
    )


class NotificationResult(BaseModel):
    """通知发送结果。"""

    incident_id: int = Field(..., description="事件 ID")
    total_channels: int = Field(0, description="通知渠道总数")
    sent_count: int = Field(0, description="成功发送数")
    failed_count: int = Field(0, description="失败数")
    results: list[dict[str, Any]] = Field(default_factory=list, description="各渠道发送结果明细")
    errors: list[str] = Field(default_factory=list, description="发送错误列表")


__all__ = [
    "CHANNEL_TYPES",
    "CaseLibraryBase",
    "CaseLibraryCreate",
    "CaseLibraryListResponse",
    "CaseLibraryQueryParams",
    "CaseLibraryResponse",
    "CaseLibraryUpdate",
    "EVIDENCE_TYPES",
    "EvidenceCollection",
    "ForensicCollectionRequest",
    "ForensicCollectionResult",
    "ForensicEvidenceBase",
    "ForensicEvidenceCreate",
    "ForensicEvidenceListResponse",
    "ForensicEvidenceQueryParams",
    "ForensicEvidenceResponse",
    "ForensicEvidenceUpdate",
    "IncidentCloseAndReviewRequest",
    "IncidentCloseRequest",
    "IncidentReview",
    "IncidentReviewBase",
    "IncidentReviewCreate",
    "IncidentReviewListResponse",
    "IncidentReviewResponse",
    "IncidentReviewUpdate",
    "NOTIFICATION_STATUSES",
    "NotificationChannelBase",
    "NotificationChannelConfig",
    "NotificationChannelCreate",
    "NotificationChannelListResponse",
    "NotificationChannelResponse",
    "NotificationChannelUpdate",
    "NotificationLogListResponse",
    "NotificationLogResponse",
    "NotificationRequest",
    "NotificationResult",
    "NotificationSendRequest",
    "NotificationSendResult",
    "REMEDIATION_ACTION_TYPES",
    "REMEDIATION_PRIORITIES",
    "REMEDIATION_STATUSES",
    "RemediationActionBase",
    "RemediationActionCreate",
    "RemediationActionListResponse",
    "RemediationActionQueryParams",
    "RemediationActionResponse",
    "RemediationActionUpdate",
    "RemediationSuggestion",
    "RemediationSuggestionList",
    "RemediationSuggestionRequest",
    "RemediationSuggestionResult",
    "SEVERITY_LEVELS",
]
