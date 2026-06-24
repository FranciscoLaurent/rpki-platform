"""API Key 相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    """创建 API Key 请求。"""

    name: str = Field(..., min_length=1, max_length=255, description="密钥名称")
    scopes: list[str] = Field(
        default_factory=list, description="权限范围列表（如 prefix:read）"
    )
    expires_at: datetime | None = Field(
        None, description="过期时间，为空表示永不过期"
    )


class ApiKeyUpdate(BaseModel):
    """更新 API Key 请求。"""

    name: str | None = Field(None, min_length=1, max_length=255, description="密钥名称")
    scopes: list[str] | None = Field(None, description="权限范围列表")
    is_active: bool | None = Field(None, description="是否启用")
    expires_at: datetime | None = Field(None, description="过期时间")


class ApiKeyResponse(BaseModel):
    """API Key 响应（不含明文密钥）。

    明文密钥仅在创建时通过 ``ApiKeyCreateResponse`` 返回一次。
    """

    id: int
    name: str
    key_prefix: str = Field(..., description="密钥前缀（用于识别）")
    user_id: int
    tenant_id: int | None = None
    scopes: list[str] = Field(default_factory=list)
    is_active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateResponse(ApiKeyResponse):
    """创建 API Key 响应（含明文密钥，仅创建时返回）。"""

    key: str = Field(..., description="明文密钥（仅此一次返回，请妥善保存）")


class ApiKeyListResponse(BaseModel):
    """API Key 列表响应。"""

    items: list[ApiKeyResponse] = Field(default_factory=list)
    total: int = Field(0, description="总数")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(50, description="返回记录数上限")


__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreateResponse",
    "ApiKeyListResponse",
    "ApiKeyResponse",
    "ApiKeyUpdate",
]
