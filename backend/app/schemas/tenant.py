"""租户相关 Pydantic 模式。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    """创建租户请求。"""

    name: str = Field(..., min_length=1, max_length=255, description="租户名称")
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$", description="租户短标识")
    settings: dict[str, Any] = Field(default_factory=dict, description="租户配置")
    max_users: int = Field(default=100, ge=1, description="最大用户数")


class TenantUpdate(BaseModel):
    """更新租户请求，所有字段可选。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="租户名称")
    status: str | None = Field(None, description="租户状态")
    settings: dict[str, Any] | None = Field(None, description="租户配置")
    max_users: int | None = Field(None, ge=1, description="最大用户数")

    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """校验租户状态取值。"""
        if v is None:
            return v
        allowed = {"active", "suspended", "disabled"}
        if v not in allowed:
            raise ValueError(f"status 必须为 {allowed} 之一")
        return v


class TenantResponse(BaseModel):
    """租户响应。"""

    id: int
    name: str
    slug: str
    status: str
    settings: dict[str, Any]
    max_users: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantListResponse(BaseModel):
    """租户列表响应（带分页信息）。"""

    items: list[TenantResponse] = Field(default_factory=list)
    total: int = Field(0, description="总数")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(50, description="返回记录数上限")


class TenantMemberCreate(BaseModel):
    """添加租户成员请求。"""

    user_id: int = Field(..., description="用户 ID")
    role: str = Field(default="member", description="租户内角色")


class TenantMemberUpdate(BaseModel):
    """更新租户成员角色请求。"""

    role: str = Field(..., description="租户内角色")


class TenantMemberResponse(BaseModel):
    """租户成员响应。"""

    id: int
    user_id: int
    tenant_id: int
    role: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantMemberListResponse(BaseModel):
    """租户成员列表响应。"""

    items: list[TenantMemberResponse] = Field(default_factory=list)
    total: int = Field(0, description="总数")


class TenantSettingsUpdate(BaseModel):
    """更新租户配置请求。"""

    settings: dict[str, Any] = Field(..., description="租户配置")


__all__ = [
    "TenantCreate",
    "TenantListResponse",
    "TenantMemberCreate",
    "TenantMemberListResponse",
    "TenantMemberResponse",
    "TenantMemberUpdate",
    "TenantResponse",
    "TenantSettingsUpdate",
    "TenantUpdate",
]
