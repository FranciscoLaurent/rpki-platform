"""ASN 相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ASNBase(BaseModel):
    """ASN 基础字段。"""

    asn: int = Field(..., ge=1, le=4294967295, description="AS 号码")
    name: str = Field(..., min_length=1, max_length=255, description="AS 名称")
    asn_type: str = Field(
        default="provider",
        description=("AS 关系类型：own/customer/provider/peer/ixp/route_server/scrubber"),
    )
    status: str = Field(default="active", description="状态：active/inactive")
    risk_profile: str | None = Field(None, description="风险画像描述")
    contact_name: str | None = Field(None, description="联系人姓名")
    contact_email: str | None = Field(None, description="联系人邮箱")
    noc_phone: str | None = Field(None, description="NOC 联系电话")
    emergency_contact: str | None = Field(None, description="紧急联系方式")
    relationship_tags: list[str] = Field(default_factory=list, description="关系标签列表")
    description: str | None = Field(None, description="描述")

    @field_validator("asn_type")
    @classmethod
    def validate_asn_type(cls, v: str) -> str:
        """校验 AS 关系类型取值。"""
        allowed = {
            "own",
            "customer",
            "provider",
            "peer",
            "ixp",
            "route_server",
            "scrubber",
        }
        if v not in allowed:
            raise ValueError(f"asn_type 必须为 {allowed} 之一")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """校验状态取值。"""
        allowed = {"active", "inactive"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


class ASNCreate(ASNBase):
    """创建 ASN 请求。"""


class ASNUpdate(BaseModel):
    """更新 ASN 请求，所有字段可选。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="AS 名称")
    asn_type: str | None = Field(None, description="AS 关系类型")
    status: str | None = Field(None, description="状态")
    risk_profile: str | None = Field(None, description="风险画像描述")
    contact_name: str | None = Field(None, description="联系人姓名")
    contact_email: str | None = Field(None, description="联系人邮箱")
    noc_phone: str | None = Field(None, description="NOC 联系电话")
    emergency_contact: str | None = Field(None, description="紧急联系方式")
    relationship_tags: list[str] | None = Field(None, description="关系标签列表")
    description: str | None = Field(None, description="描述")

    @field_validator("asn_type")
    @classmethod
    def validate_asn_type(cls, v: str | None) -> str | None:
        """校验 AS 关系类型取值。"""
        if v is None:
            return v
        allowed = {
            "own",
            "customer",
            "provider",
            "peer",
            "ixp",
            "route_server",
            "scrubber",
        }
        if v not in allowed:
            raise ValueError(f"asn_type 必须为 {allowed} 之一")
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


class ASNResponse(BaseModel):
    """ASN 响应。"""

    id: int
    asn: int
    name: str
    asn_type: str
    status: str
    risk_profile: str | None
    contact_name: str | None
    contact_email: str | None
    noc_phone: str | None
    emergency_contact: str | None
    relationship_tags: list[str] | None
    description: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ASNListResponse(BaseModel):
    """ASN 列表响应（带分页信息）。"""

    items: list[ASNResponse]
    total: int
    skip: int
    limit: int


__all__ = [
    "ASNBase",
    "ASNCreate",
    "ASNListResponse",
    "ASNResponse",
    "ASNUpdate",
]
