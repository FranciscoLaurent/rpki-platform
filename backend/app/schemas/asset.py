"""业务服务、客户、路由器相关 Pydantic 模式，以及资产一致性检查与关系视图。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ──────────────────────────────────────────────
# 业务服务
# ──────────────────────────────────────────────


class BusinessServiceBase(BaseModel):
    """业务服务基础字段。"""

    name: str = Field(..., min_length=1, max_length=255, description="业务服务名称")
    description: str | None = Field(None, description="业务描述")
    importance: str = Field(
        default="normal", description="重要度：critical/important/normal/low"
    )
    owner_contact: str | None = Field(None, description="业务负责人联系方式")

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str) -> str:
        """校验重要度取值。"""
        allowed = {"critical", "important", "normal", "low"}
        if v not in allowed:
            raise ValueError(f"importance 必须为 {allowed} 之一")
        return v


class BusinessServiceCreate(BusinessServiceBase):
    """创建业务服务请求。"""


class BusinessServiceUpdate(BaseModel):
    """更新业务服务请求，所有字段可选。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="业务服务名称")
    description: str | None = Field(None, description="业务描述")
    importance: str | None = Field(None, description="重要度")
    owner_contact: str | None = Field(None, description="业务负责人联系方式")

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str | None) -> str | None:
        """校验重要度取值。"""
        if v is None:
            return v
        allowed = {"critical", "important", "normal", "low"}
        if v not in allowed:
            raise ValueError(f"importance 必须为 {allowed} 之一")
        return v


class BusinessServiceResponse(BaseModel):
    """业务服务响应。"""

    id: int
    name: str
    description: str | None
    importance: str
    owner_contact: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessServiceListResponse(BaseModel):
    """业务服务列表响应。"""

    items: list[BusinessServiceResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# 客户
# ──────────────────────────────────────────────


class CustomerBase(BaseModel):
    """客户基础字段。"""

    name: str = Field(..., min_length=1, max_length=255, description="客户名称")
    contact_name: str | None = Field(None, description="客户联系人姓名")
    contact_email: str | None = Field(None, description="客户联系人邮箱")
    contract_id: str | None = Field(None, description="合同编号")
    service_level: str = Field(
        default="standard", description="服务等级：standard/silver/gold/platinum"
    )
    status: str = Field(default="active", description="状态：active/inactive")

    @field_validator("service_level")
    @classmethod
    def validate_service_level(cls, v: str) -> str:
        """校验服务等级取值。"""
        allowed = {"standard", "silver", "gold", "platinum"}
        if v not in allowed:
            raise ValueError(f"service_level 必须为 {allowed} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态取值。"""
        allowed = {"active", "inactive"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


class CustomerCreate(CustomerBase):
    """创建客户请求。"""


class CustomerUpdate(BaseModel):
    """更新客户请求，所有字段可选。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="客户名称")
    contact_name: str | None = Field(None, description="客户联系人姓名")
    contact_email: str | None = Field(None, description="客户联系人邮箱")
    contract_id: str | None = Field(None, description="合同编号")
    service_level: str | None = Field(None, description="服务等级")
    status: str | None = Field(None, description="状态")

    @field_validator("service_level")
    @classmethod
    def validate_service_level(cls, v: str | None) -> str | None:
        """校验服务等级取值。"""
        if v is None:
            return v
        allowed = {"standard", "silver", "gold", "platinum"}
        if v not in allowed:
            raise ValueError(f"service_level 必须为 {allowed} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态取值。"""
        if v is None:
            return v
        allowed = {"active", "inactive"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


class CustomerResponse(BaseModel):
    """客户响应。"""

    id: int
    name: str
    contact_name: str | None
    contact_email: str | None
    contract_id: str | None
    service_level: str
    status: str
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerListResponse(BaseModel):
    """客户列表响应。"""

    items: list[CustomerResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# 路由器
# ──────────────────────────────────────────────


class RouterBase(BaseModel):
    """路由器基础字段。"""

    hostname: str = Field(..., min_length=1, max_length=255, description="主机名")
    vendor: str | None = Field(None, description="厂商")
    model: str | None = Field(None, description="设备型号")
    management_ip: str | None = Field(None, description="管理 IP 地址")
    location: str | None = Field(None, description="部署位置")
    snmp_community: str | None = Field(None, description="SNMP community 字符串")
    status: str = Field(
        default="active", description="状态：active/inactive/maintenance"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态取值。"""
        allowed = {"active", "inactive", "maintenance"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


class RouterCreate(RouterBase):
    """创建路由器请求。"""


class RouterUpdate(BaseModel):
    """更新路由器请求，所有字段可选。"""

    hostname: str | None = Field(None, min_length=1, max_length=255, description="主机名")
    vendor: str | None = Field(None, description="厂商")
    model: str | None = Field(None, description="设备型号")
    management_ip: str | None = Field(None, description="管理 IP 地址")
    location: str | None = Field(None, description="部署位置")
    snmp_community: str | None = Field(None, description="SNMP community 字符串")
    status: str | None = Field(None, description="状态")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态取值。"""
        if v is None:
            return v
        allowed = {"active", "inactive", "maintenance"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


class RouterResponse(BaseModel):
    """路由器响应。"""

    id: int
    hostname: str
    vendor: str | None
    model: str | None
    management_ip: str | None
    location: str | None
    snmp_community: str | None
    status: str
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RouterListResponse(BaseModel):
    """路由器列表响应。"""

    items: list[RouterResponse]
    total: int
    skip: int
    limit: int


# ──────────────────────────────────────────────
# 资产一致性检查与关系视图
# ──────────────────────────────────────────────


class ConsistencyCheckItem(BaseModel):
    """一致性检查单项结果。"""

    type: str = Field(..., description="不一致类型，如 unregistered_prefix/expired/status_mismatch")
    prefix: str | None = Field(None, description="相关前缀")
    description: str = Field(..., description="问题描述")
    severity: str = Field(..., description="严重等级：info/warning/critical")


class ConsistencyCheckResult(BaseModel):
    """资产一致性检查结果。"""

    items: list[ConsistencyCheckItem] = Field(
        default_factory=list, description="不一致项列表"
    )
    total: int = Field(..., description="不一致项总数")
    critical_count: int = Field(..., description="critical 数量")
    warning_count: int = Field(..., description="warning 数量")
    info_count: int = Field(..., description="info 数量")
    checked_at: datetime = Field(..., description="检查时间")


class RelationshipView(BaseModel):
    """前缀—ASN—ROA—BGP—业务—事件关联视图。

    目前为基础版实现，仅返回前缀与已登记的关联资源。
    """

    prefix: dict[str, Any] = Field(..., description="前缀信息")
    parent: dict[str, Any] | None = Field(None, description="父前缀信息")
    children: list[dict[str, Any]] = Field(
        default_factory=list, description="子前缀列表"
    )
    customer: dict[str, Any] | None = Field(None, description="关联客户信息")
    business_service: dict[str, Any] | None = Field(
        None, description="关联业务服务信息"
    )
    bgp_peers: list[dict[str, Any]] = Field(
        default_factory=list, description="关联 BGP 邻居列表"
    )
    related_asns: list[dict[str, Any]] = Field(
        default_factory=list, description="关联 ASN 列表"
    )


__all__ = [
    "BusinessServiceBase",
    "BusinessServiceCreate",
    "BusinessServiceListResponse",
    "BusinessServiceResponse",
    "BusinessServiceUpdate",
    "ConsistencyCheckItem",
    "ConsistencyCheckResult",
    "CustomerBase",
    "CustomerCreate",
    "CustomerListResponse",
    "CustomerResponse",
    "CustomerUpdate",
    "RelationshipView",
    "RouterBase",
    "RouterCreate",
    "RouterListResponse",
    "RouterResponse",
    "RouterUpdate",
]
