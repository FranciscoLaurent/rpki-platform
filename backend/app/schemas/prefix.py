"""IP 前缀相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

import ipaddress
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrefixBase(BaseModel):
    """前缀基础字段。"""

    prefix: str = Field(..., description="CIDR 表示的 IP 前缀，如 192.168.1.0/24")
    importance: str = Field(
        default="normal",
        description="重要度：critical/important/normal/low",
    )
    business_service: str | None = Field(None, description="业务归属")
    region: str | None = Field(None, description="地域")
    site: str | None = Field(None, description="机房")
    cloud_zone: str | None = Field(None, description="云区域")
    customer_id: int | None = Field(None, description="关联客户 ID")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    description: str | None = Field(None, description="描述")
    status: str = Field(default="active", description="状态")

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        """校验 CIDR 格式并规范化输出。"""
        try:
            net = ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"无效的 CIDR 前缀: {e}") from e
        return str(net)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态取值。"""
        allowed = {"active", "inactive", "reserved", "deprecated"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str) -> str:
        """校验重要度取值。"""
        allowed = {"critical", "important", "normal", "low"}
        if v not in allowed:
            raise ValueError(f"importance 必须为 {allowed} 之一")
        return v


class PrefixCreate(PrefixBase):
    """创建前缀请求。"""

    registered_at: datetime | None = Field(None, description="登记时间")
    expired_at: datetime | None = Field(None, description="过期时间")


class PrefixUpdate(BaseModel):
    """更新前缀请求，所有字段可选。"""

    prefix: str | None = Field(None, description="CIDR 表示的 IP 前缀")
    importance: str | None = Field(None, description="重要度")
    business_service: str | None = Field(None, description="业务归属")
    region: str | None = Field(None, description="地域")
    site: str | None = Field(None, description="机房")
    cloud_zone: str | None = Field(None, description="云区域")
    customer_id: int | None = Field(None, description="关联客户 ID")
    tags: list[str] | None = Field(None, description="标签列表")
    description: str | None = Field(None, description="描述")
    status: str | None = Field(None, description="状态")
    parent_id: int | None = Field(None, description="父前缀 ID")
    registered_at: datetime | None = Field(None, description="登记时间")
    expired_at: datetime | None = Field(None, description="过期时间")

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str | None) -> str | None:
        """校验 CIDR 格式。"""
        if v is None:
            return v
        try:
            net = ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"无效的 CIDR 前缀: {e}") from e
        return str(net)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验状态取值。"""
        if v is None:
            return v
        allowed = {"active", "inactive", "reserved", "deprecated"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v

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


class PrefixResponse(BaseModel):
    """前缀响应。"""

    id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    parent_id: int | None
    status: str
    importance: str
    business_service: str | None
    region: str | None
    site: str | None
    cloud_zone: str | None
    customer_id: int | None
    tags: list[str] | None
    description: str | None
    registered_at: datetime | None
    expired_at: datetime | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrefixTreeNode(PrefixResponse):
    """前缀树节点，递归包含子前缀。"""

    children: list[PrefixTreeNode] = Field(default_factory=list, description="子前缀列表")


class PrefixBatchImport(BaseModel):
    """批量导入前缀请求。"""

    prefixes: list[PrefixCreate] = Field(..., description="待导入的前缀列表")


class PrefixBatchImportError(BaseModel):
    """批量导入失败的明细。"""

    index: int = Field(..., description="失败项在列表中的索引")
    prefix: str = Field(..., description="失败的前缀")
    error: str = Field(..., description="失败原因")


class PrefixBatchImportResult(BaseModel):
    """批量导入结果。"""

    total: int = Field(..., description="总数")
    success: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    errors: list[PrefixBatchImportError] = Field(default_factory=list, description="失败明细列表")


class PrefixListResponse(BaseModel):
    """前缀列表响应（带分页信息）。"""

    items: list[PrefixResponse]
    total: int
    skip: int
    limit: int


# 解决前向引用
PrefixTreeNode.model_rebuild()


__all__ = [
    "PrefixBase",
    "PrefixBatchImport",
    "PrefixBatchImportError",
    "PrefixBatchImportResult",
    "PrefixCreate",
    "PrefixListResponse",
    "PrefixResponse",
    "PrefixTreeNode",
    "PrefixUpdate",
]
