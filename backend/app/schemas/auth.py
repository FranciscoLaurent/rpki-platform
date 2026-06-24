"""认证相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """令牌响应。"""

    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="访问令牌有效期（秒）")
    refresh_token: str = Field(..., description="刷新令牌")
    must_change_password: bool = Field(default=False, description="是否需要修改密码")


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求。"""

    refresh_token: str = Field(..., description="刷新令牌")


class UserCreate(BaseModel):
    """用户注册请求。"""

    email: str = Field(..., description="邮箱地址")
    username: str = Field(..., min_length=3, max_length=100, description="用户名")
    full_name: str | None = Field(None, description="姓名")
    password: str = Field(..., min_length=8, max_length=128, description="密码")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """简单邮箱格式校验。"""
        if "@" not in v or "." not in v:
            raise ValueError("邮箱格式不正确")
        return v.lower().strip()


class UserUpdate(BaseModel):
    """用户更新请求。"""

    full_name: str | None = Field(None, description="姓名")
    password: str | None = Field(None, min_length=8, max_length=128, description="新密码")
    is_active: bool | None = Field(None, description="是否启用")


class RoleResponse(BaseModel):
    """角色响应。"""

    id: int
    name: str
    code: str
    permissions: list[str] = Field(default_factory=list, description="权限编码列表")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("permissions", mode="before")
    @classmethod
    def extract_permission_codes(cls, v: Any) -> Any:
        """从 Permission 对象列表中提取权限编码。"""
        if isinstance(v, list) and v:
            first = v[0]
            if hasattr(first, "code"):
                return [p.code for p in v]
        return v


class UserResponse(BaseModel):
    """用户响应。"""

    id: int
    email: str
    username: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    roles: list[RoleResponse] = Field(default_factory=list)
    created_at: datetime
    must_change_password: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    """修改密码请求。"""

    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")


class AssignRolesRequest(BaseModel):
    """分配角色请求。"""

    role_ids: list[int] = Field(..., description="角色 ID 列表")


class MessageResponse(BaseModel):
    """通用消息响应。"""

    message: str
