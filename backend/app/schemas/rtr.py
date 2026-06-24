"""RPKI-RTR 服务与设备配置相关 Pydantic 模式（请求与响应）。

包含 RTR 服务 CRUD、客户端会话、序列号历史、设备配置模板 CRUD、
设备配置生成、服务状态与一致性检查等模式。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ──────────────────────────────────────────────
# RTR 服务 CRUD
# ──────────────────────────────────────────────


class RTRServerBase(BaseModel):
    """RTR 服务基础字段。"""

    name: str = Field(..., description="RTR 服务名称")
    listen_host: str = Field(default="0.0.0.0", description="监听地址")
    listen_port: int = Field(
        default=8282, ge=1, le=65535, description="监听端口"
    )
    session_id: int = Field(
        default=1, ge=0, le=65535, description="RTR Session ID"
    )
    mtls_enabled: bool = Field(
        default=False, description="是否启用 mTLS 双向认证"
    )
    whitelist: list[str] | None = Field(
        None, description="允许连接的客户端 IP 列表"
    )
    config: dict[str, Any] | None = Field(
        None, description="其他配置（如刷新间隔、超时等）"
    )


class RTRServerCreate(RTRServerBase):
    """创建 RTR 服务请求。"""


class RTRServerUpdate(BaseModel):
    """更新 RTR 服务请求，所有字段可选。"""

    name: str | None = Field(None, description="RTR 服务名称")
    listen_host: str | None = Field(None, description="监听地址")
    listen_port: int | None = Field(
        None, ge=1, le=65535, description="监听端口"
    )
    session_id: int | None = Field(
        None, ge=0, le=65535, description="RTR Session ID"
    )
    mtls_enabled: bool | None = Field(
        None, description="是否启用 mTLS 双向认证"
    )
    whitelist: list[str] | None = Field(
        None, description="允许连接的客户端 IP 列表"
    )
    config: dict[str, Any] | None = Field(
        None, description="其他配置（如刷新间隔、超时等）"
    )


class RTRServerResponse(BaseModel):
    """RTR 服务响应。"""

    id: int
    name: str
    listen_host: str
    listen_port: int
    session_id: int
    current_serial: int
    status: str
    vrps_count: int
    connected_clients: int
    mtls_enabled: bool
    whitelist: list[str] | None
    config: dict[str, Any] | None
    last_started_at: datetime | None
    last_error: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RTRServerListResponse(BaseModel):
    """RTR 服务列表响应（带分页信息）。"""

    items: list[RTRServerResponse] = Field(default_factory=list)
    total: int = Field(0, description="总记录数")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(50, description="返回记录数上限")


# ──────────────────────────────────────────────
# RTR 客户端会话
# ──────────────────────────────────────────────


class RTRSessionResponse(BaseModel):
    """RTR 客户端会话响应。"""

    id: int
    server_id: int
    client_ip: str
    client_port: int | None
    client_version: int | None
    session_state: str
    last_serial: int | None
    connected_at: datetime | None
    last_activity_at: datetime | None
    bytes_sent: int
    bytes_received: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RTRSessionListResponse(BaseModel):
    """RTR 客户端会话列表响应。"""

    items: list[RTRSessionResponse] = Field(default_factory=list)
    total: int = Field(0, description="总记录数")


# ──────────────────────────────────────────────
# 序列号历史
# ──────────────────────────────────────────────


class RTRSerialHistoryResponse(BaseModel):
    """RTR 序列号历史响应。"""

    id: int
    server_id: int
    serial_number: int
    change_type: str
    vrps_added: int
    vrps_removed: int
    vrps_modified: int
    snapshot_id: int | None
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RTRSerialHistoryListResponse(BaseModel):
    """RTR 序列号历史列表响应。"""

    items: list[RTRSerialHistoryResponse] = Field(default_factory=list)
    total: int = Field(0, description="总记录数")


# ──────────────────────────────────────────────
# RTR 服务状态与操作响应
# ──────────────────────────────────────────────


class RTRServerStatus(BaseModel):
    """RTR 服务运行状态。"""

    server_id: int = Field(..., description="RTR 服务 ID")
    status: str = Field(..., description="服务状态：running/stopped/error")
    vrps_count: int = Field(0, description="当前 VRP 数量")
    connected_clients: int = Field(
        0, description="当前连接客户端数"
    )
    uptime: int = Field(0, description="运行时长（秒）")
    current_serial: int = Field(0, description="当前序列号")
    session_id: int = Field(..., description="RTR Session ID")
    last_error: str | None = Field(None, description="最近错误信息")


class RTRServerActionResponse(BaseModel):
    """RTR 服务操作（启动/停止/更新/回滚）响应。"""

    server_id: int
    status: str = Field(..., description="操作后的服务状态")
    message: str = Field(..., description="操作结果消息")
    serial_number: int | None = Field(
        None, description="操作涉及的序列号（如有）"
    )


class RTRConsistencyDifference(BaseModel):
    """RTR 一致性检查差异项。"""

    prefix: str = Field(..., description="网络前缀")
    origin_as: int = Field(..., description="起源 AS 号")
    difference_type: str = Field(
        ...,
        description=(
            "差异类型：only_in_server（仅服务端有）、"
            "only_in_db（仅数据库有）、max_length_mismatch（maxLength 不一致）"
        ),
    )
    server_max_length: int | None = Field(
        None, description="服务端的 maxLength"
    )
    db_max_length: int | None = Field(
        None, description="数据库的 maxLength"
    )


class RTRConsistencyCheckResult(BaseModel):
    """RTR 一致性检查结果。"""

    server_id: int
    consistent: bool = Field(..., description="是否一致")
    server_vrps_count: int = Field(0, description="服务端 VRP 数量")
    db_vrps_count: int = Field(0, description="数据库 VRP 数量")
    differences: list[RTRConsistencyDifference] = Field(
        default_factory=list, description="差异列表"
    )


class RTRRollbackRequest(BaseModel):
    """RTR 序列号回滚请求。"""

    target_serial: int = Field(
        ..., ge=0, description="目标序列号"
    )


# ──────────────────────────────────────────────
# 设备配置模板 CRUD
# ──────────────────────────────────────────────


class DeviceConfigTemplateBase(BaseModel):
    """设备配置模板基础字段。"""

    name: str = Field(..., description="模板名称")
    vendor: str = Field(
        ...,
        description=(
            "厂商：cisco_ios_xe/cisco_ios_xr/juniper_junos/huawei_vrp/"
            "h3c/arista_eos/nokia_sros/frr/bird/openbgpd"
        ),
    )
    template_type: str = Field(
        ...,
        description="模板类型：rtr_client/rov_policy/rollback/risk_notice",
    )
    content: str = Field(..., description="模板内容，含变量占位符")
    variables: dict[str, Any] | None = Field(
        None, description="变量定义"
    )
    description: str | None = Field(None, description="模板描述")
    enabled: bool = Field(True, description="是否启用")

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str) -> str:
        """校验厂商取值。"""
        allowed = {
            "cisco_ios_xe",
            "cisco_ios_xr",
            "juniper_junos",
            "huawei_vrp",
            "h3c",
            "arista_eos",
            "nokia_sros",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"vendor 必须为 {sorted(allowed)} 之一")
        return v

    @field_validator("template_type")
    @classmethod
    def validate_template_type(cls, v: str) -> str:
        """校验模板类型取值。"""
        allowed = {"rtr_client", "rov_policy", "rollback", "risk_notice"}
        if v not in allowed:
            raise ValueError(f"template_type 必须为 {sorted(allowed)} 之一")
        return v


class DeviceConfigTemplateCreate(DeviceConfigTemplateBase):
    """创建设备配置模板请求。"""


class DeviceConfigTemplateUpdate(BaseModel):
    """更新设备配置模板请求，所有字段可选。"""

    name: str | None = Field(None, description="模板名称")
    vendor: str | None = Field(None, description="厂商")
    template_type: str | None = Field(None, description="模板类型")
    content: str | None = Field(None, description="模板内容")
    variables: dict[str, Any] | None = Field(None, description="变量定义")
    description: str | None = Field(None, description="模板描述")
    enabled: bool | None = Field(None, description="是否启用")

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str | None) -> str | None:
        """校验厂商取值。"""
        if v is None:
            return v
        allowed = {
            "cisco_ios_xe",
            "cisco_ios_xr",
            "juniper_junos",
            "huawei_vrp",
            "h3c",
            "arista_eos",
            "nokia_sros",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"vendor 必须为 {sorted(allowed)} 之一")
        return v

    @field_validator("template_type")
    @classmethod
    def validate_template_type(cls, v: str | None) -> str | None:
        """校验模板类型取值。"""
        if v is None:
            return v
        allowed = {"rtr_client", "rov_policy", "rollback", "risk_notice"}
        if v not in allowed:
            raise ValueError(f"template_type 必须为 {sorted(allowed)} 之一")
        return v


class DeviceConfigTemplateResponse(BaseModel):
    """设备配置模板响应。"""

    id: int
    name: str
    vendor: str
    template_type: str
    content: str
    variables: dict[str, Any] | None
    description: str | None
    enabled: bool
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeviceConfigTemplateListResponse(BaseModel):
    """设备配置模板列表响应。"""

    items: list[DeviceConfigTemplateResponse] = Field(default_factory=list)
    total: int = Field(0, description="总记录数")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(50, description="返回记录数上限")


# ──────────────────────────────────────────────
# 设备配置生成
# ──────────────────────────────────────────────


class DeviceConfigRequest(BaseModel):
    """设备配置生成请求。"""

    vendor: str = Field(..., description="厂商")
    template_type: str = Field(
        default="rtr_client", description="模板类型"
    )
    variables: dict[str, Any] = Field(
        default_factory=dict, description="变量字典"
    )

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str) -> str:
        """校验厂商取值。"""
        allowed = {
            "cisco_ios_xe",
            "cisco_ios_xr",
            "juniper_junos",
            "huawei_vrp",
            "h3c",
            "arista_eos",
            "nokia_sros",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"vendor 必须为 {sorted(allowed)} 之一")
        return v


class DeviceConfigResult(BaseModel):
    """设备配置生成结果。"""

    generated_config: str = Field(..., description="生成的配置文本")
    warnings: list[str] = Field(
        default_factory=list, description="警告信息列表"
    )
    vendor: str = Field(..., description="厂商")
    template_type: str = Field(..., description="模板类型")
    template_id: int | None = Field(
        None, description="使用的模板 ID（如为默认模板则为 None）"
    )


class VendorInfo(BaseModel):
    """厂商信息。"""

    vendor: str = Field(..., description="厂商代码")
    name: str = Field(..., description="厂商显示名称")
    template_types: list[str] = Field(
        default_factory=list, description="支持的模板类型"
    )


class VendorListResponse(BaseModel):
    """厂商列表响应。"""

    vendors: list[VendorInfo] = Field(default_factory=list)


class DefaultTemplateResponse(BaseModel):
    """厂商默认模板响应。"""

    vendor: str = Field(..., description="厂商代码")
    templates: list[DeviceConfigTemplateResponse] = Field(
        default_factory=list, description="默认模板列表"
    )


# ──────────────────────────────────────────────
# ROV 策略查询
# ──────────────────────────────────────────────


class PolicyInfo(BaseModel):
    """ROV 策略信息。"""

    policy: str = Field(..., description="策略代码")
    name: str = Field(..., description="策略显示名称")
    description: str = Field(..., description="策略描述")


class PolicyListResponse(BaseModel):
    """ROV 策略列表响应。"""

    policies: list[PolicyInfo] = Field(default_factory=list)


class PolicyTemplateInfo(BaseModel):
    """厂商策略模板信息。"""

    policy: str = Field(..., description="策略代码")
    name: str = Field(..., description="策略显示名称")
    content: str = Field(..., description="模板内容")


class PolicyTemplateListResponse(BaseModel):
    """厂商策略模板列表响应。"""

    vendor: str = Field(..., description="厂商代码")
    policies: list[PolicyTemplateInfo] = Field(
        default_factory=list, description="策略模板列表"
    )


# ──────────────────────────────────────────────
# 按策略生成配置
# ──────────────────────────────────────────────


class DeviceConfigPolicyRequest(BaseModel):
    """按 ROV 策略生成设备配置请求。"""

    vendor: str = Field(..., description="厂商")
    policy: str = Field(
        ...,
        description=(
            "ROV 策略：drop_invalid/de_preference_invalid/monitor_only"
        ),
    )
    variables: dict[str, Any] = Field(
        default_factory=dict, description="变量字典"
    )

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str) -> str:
        """校验厂商取值。"""
        allowed = {
            "cisco_ios_xe",
            "cisco_ios_xr",
            "juniper_junos",
            "huawei_vrp",
            "h3c",
            "arista_eos",
            "nokia_sros",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"vendor 必须为 {sorted(allowed)} 之一")
        return v

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, v: str) -> str:
        """校验策略取值。"""
        allowed = {"drop_invalid", "de_preference_invalid", "monitor_only"}
        if v not in allowed:
            raise ValueError(f"policy 必须为 {sorted(allowed)} 之一")
        return v


class DeviceConfigPolicyResult(BaseModel):
    """按策略生成配置结果。"""

    generated_config: str = Field(..., description="生成的配置文本")
    warnings: list[str] = Field(
        default_factory=list, description="警告信息列表"
    )
    vendor: str = Field(..., description="厂商")
    policy: str = Field(..., description="使用的 ROV 策略")


# ──────────────────────────────────────────────
# 批量生成配置
# ──────────────────────────────────────────────


class DeviceConfigBatchItem(BaseModel):
    """批量生成配置中的单个设备请求。"""

    device_name: str = Field(..., description="设备名称（用于标识）")
    vendor: str = Field(..., description="厂商")
    template_type: str = Field(
        default="rtr_client", description="模板类型"
    )
    variables: dict[str, Any] = Field(
        default_factory=dict, description="变量字典"
    )

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str) -> str:
        """校验厂商取值。"""
        allowed = {
            "cisco_ios_xe",
            "cisco_ios_xr",
            "juniper_junos",
            "huawei_vrp",
            "h3c",
            "arista_eos",
            "nokia_sros",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"vendor 必须为 {sorted(allowed)} 之一")
        return v


class DeviceConfigBatchRequest(BaseModel):
    """批量生成设备配置请求。"""

    items: list[DeviceConfigBatchItem] = Field(
        ..., min_length=1, max_length=100, description="设备配置生成请求列表"
    )


class DeviceConfigBatchResultItem(BaseModel):
    """批量生成配置结果中的单个设备结果。"""

    device_name: str = Field(..., description="设备名称")
    success: bool = Field(..., description="是否生成成功")
    generated_config: str | None = Field(
        None, description="生成的配置文本（失败时为 None）"
    )
    warnings: list[str] = Field(
        default_factory=list, description="警告信息列表"
    )
    error: str | None = Field(
        None, description="错误信息（失败时存在）"
    )
    vendor: str = Field(..., description="厂商")
    template_type: str = Field(..., description="模板类型")


class DeviceConfigBatchResult(BaseModel):
    """批量生成设备配置结果。"""

    results: list[DeviceConfigBatchResultItem] = Field(
        default_factory=list, description="各设备生成结果"
    )
    total: int = Field(0, description="总设备数")
    success_count: int = Field(0, description="成功生成数")
    failure_count: int = Field(0, description="失败数")


# ──────────────────────────────────────────────
# 配置差异对比
# ──────────────────────────────────────────────


class DeviceConfigDiffRequest(BaseModel):
    """配置差异对比请求。"""

    config_a: str = Field(..., description="配置文本 A")
    config_b: str = Field(..., description="配置文本 B")
    context_lines: int = Field(
        default=3, ge=0, le=20, description="差异上下文行数"
    )


class DeviceConfigDiffEntry(BaseModel):
    """配置差异条目。"""

    line_number_a: int | None = Field(
        None, description="配置 A 中的行号（仅新增行时为 None）"
    )
    line_number_b: int | None = Field(
        None, description="配置 B 中的行号（仅删除行时为 None）"
    )
    change_type: str = Field(
        ...,
        description="变更类型：added（新增）/removed（删除）/modified（修改）",
    )
    content_a: str | None = Field(
        None, description="配置 A 中的行内容"
    )
    content_b: str | None = Field(
        None, description="配置 B 中的行内容"
    )


class DeviceConfigDiffResult(BaseModel):
    """配置差异对比结果。"""

    identical: bool = Field(..., description="两份配置是否完全相同")
    added_count: int = Field(0, description="新增行数")
    removed_count: int = Field(0, description="删除行数")
    modified_count: int = Field(0, description="修改行数")
    diff_text: str = Field(..., description="统一 diff 格式文本")
    entries: list[DeviceConfigDiffEntry] = Field(
        default_factory=list, description="差异条目列表"
    )


# ──────────────────────────────────────────────
# 配置验证
# ──────────────────────────────────────────────


class DeviceConfigValidationRequest(BaseModel):
    """配置语法验证请求。"""

    vendor: str = Field(..., description="厂商（用于选择验证规则）")
    config: str = Field(..., description="待验证的配置文本")

    @field_validator("vendor")
    @classmethod
    def validate_vendor(cls, v: str) -> str:
        """校验厂商取值。"""
        allowed = {
            "cisco_ios_xe",
            "cisco_ios_xr",
            "juniper_junos",
            "huawei_vrp",
            "h3c",
            "arista_eos",
            "nokia_sros",
            "frr",
            "bird",
            "openbgpd",
        }
        if v not in allowed:
            raise ValueError(f"vendor 必须为 {sorted(allowed)} 之一")
        return v


class DeviceConfigValidationIssue(BaseModel):
    """配置验证问题。"""

    line_number: int | None = Field(
        None, description="问题所在行号"
    )
    severity: str = Field(
        ..., description="严重级别：error/warning/info"
    )
    message: str = Field(..., description="问题描述")
    line_content: str | None = Field(
        None, description="问题行内容"
    )


class DeviceConfigValidationResult(BaseModel):
    """配置验证结果。"""

    valid: bool = Field(..., description="配置是否通过验证")
    vendor: str = Field(..., description="厂商")
    issues: list[DeviceConfigValidationIssue] = Field(
        default_factory=list, description="验证问题列表"
    )
    checked_at: datetime = Field(
        ..., description="验证时间"
    )


__all__ = [
    "DefaultTemplateResponse",
    "DeviceConfigBatchItem",
    "DeviceConfigBatchRequest",
    "DeviceConfigBatchResult",
    "DeviceConfigBatchResultItem",
    "DeviceConfigDiffEntry",
    "DeviceConfigDiffRequest",
    "DeviceConfigDiffResult",
    "DeviceConfigPolicyRequest",
    "DeviceConfigPolicyResult",
    "DeviceConfigRequest",
    "DeviceConfigResult",
    "DeviceConfigTemplateBase",
    "DeviceConfigTemplateCreate",
    "DeviceConfigTemplateListResponse",
    "DeviceConfigTemplateResponse",
    "DeviceConfigTemplateUpdate",
    "DeviceConfigValidationIssue",
    "DeviceConfigValidationRequest",
    "DeviceConfigValidationResult",
    "PolicyInfo",
    "PolicyListResponse",
    "PolicyTemplateInfo",
    "PolicyTemplateListResponse",
    "RTRConsistencyCheckResult",
    "RTRConsistencyDifference",
    "RTRRollbackRequest",
    "RTRSerialHistoryListResponse",
    "RTRSerialHistoryResponse",
    "RTRServerActionResponse",
    "RTRServerBase",
    "RTRServerCreate",
    "RTRServerListResponse",
    "RTRServerResponse",
    "RTRServerStatus",
    "RTRServerUpdate",
    "RTRSessionListResponse",
    "RTRSessionResponse",
    "VendorInfo",
    "VendorListResponse",
]
