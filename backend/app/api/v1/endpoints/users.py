"""用户管理端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.core.rbac import Permissions
from app.models.user import User
from app.schemas.auth import (
    AssignRolesRequest,
    UserResponse,
    UserUpdate,
)
from app.services import audit_service, user_service

router = APIRouter()


@router.get("", response_model=list[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.USER_READ)),
) -> list[UserResponse]:
    """获取用户列表（需要 ``user:read`` 权限）。"""
    users = await user_service.get_users(db, skip=skip, limit=limit)
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.USER_READ)),
) -> UserResponse:
    """获取用户详情（需要 ``user:read`` 权限）。"""
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID {user_id} 不存在",
        )
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.USER_WRITE)),
) -> UserResponse:
    """更新用户信息（需要 ``user:write`` 权限）。"""
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID {user_id} 不存在",
        )

    updated_user = await user_service.update_user(db, user, user_update)

    # 记录审计日志
    await audit_service.log_action(
        db,
        user_id=current_user.id,
        tenant_id=None,
        action="update_user",
        resource_type="user",
        resource_id=str(user_id),
        details=user_update.model_dump(exclude_none=True),
    )

    return UserResponse.model_validate(updated_user)


@router.post("/{user_id}/roles", response_model=UserResponse)
async def assign_roles(
    user_id: int,
    role_request: AssignRolesRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.USER_WRITE)),
) -> UserResponse:
    """为用户分配角色（需要 ``user:write`` 权限）。

    该操作会替换用户原有的全部角色。
    """
    user = await user_service.assign_roles(db, user_id, role_request.role_ids)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID {user_id} 不存在",
        )

    # 记录审计日志
    await audit_service.log_action(
        db,
        user_id=current_user.id,
        tenant_id=None,
        action="assign_roles",
        resource_type="user",
        resource_id=str(user_id),
        details={"role_ids": role_request.role_ids},
    )

    return UserResponse.model_validate(user)
