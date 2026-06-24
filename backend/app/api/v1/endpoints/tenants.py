"""租户管理 API 端点。

提供租户 CRUD、成员管理与配置管理接口。
所有接口均需对应权限，并通过 ``require_tenant_access`` 验证租户边界。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions, require_tenant_access
from app.core.database import get_db
from app.models.user import User
from app.schemas.tenant import (
    TenantCreate,
    TenantListResponse,
    TenantMemberCreate,
    TenantMemberListResponse,
    TenantMemberResponse,
    TenantMemberUpdate,
    TenantResponse,
    TenantSettingsUpdate,
    TenantUpdate,
)
from app.services import tenant_service

router = APIRouter()


# ──────────────────────────────────────────────
# 租户 CRUD
# ──────────────────────────────────────────────


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    payload: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:write")),
) -> TenantResponse:
    """创建租户（需要 ``tenant:write`` 权限）。"""
    try:
        tenant = await tenant_service.create_tenant(db, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return TenantResponse.model_validate(tenant)


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    name: str | None = Query(None, description="按名称模糊过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:read")),
) -> TenantListResponse:
    """获取租户列表（需要 ``tenant:read`` 权限）。"""
    filters: dict[str, object] = {}
    if status_filter is not None:
        filters["status"] = status_filter
    if name is not None:
        filters["name"] = name

    items = await tenant_service.get_tenants(db, filters=filters, skip=skip, limit=limit)
    total = await tenant_service.count_tenants(db, filters=filters)
    return TenantListResponse(
        items=[TenantResponse.model_validate(t) for t in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:read")),
    _: None = Depends(require_tenant_access),
) -> TenantResponse:
    """获取租户详情（需要 ``tenant:read`` 权限）。"""
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 ID {tenant_id} 不存在",
        )
    return TenantResponse.model_validate(tenant)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:write")),
    _: None = Depends(require_tenant_access),
) -> TenantResponse:
    """更新租户信息（需要 ``tenant:write`` 权限）。"""
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 ID {tenant_id} 不存在",
        )
    updated = await tenant_service.update_tenant(db, tenant, payload)
    return TenantResponse.model_validate(updated)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:delete")),
    _: None = Depends(require_tenant_access),
) -> None:
    """删除租户（需要 ``tenant:delete`` 权限）。"""
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 ID {tenant_id} 不存在",
        )
    await tenant_service.delete_tenant(db, tenant)


# ──────────────────────────────────────────────
# 租户配置管理
# ──────────────────────────────────────────────


@router.get("/{tenant_id}/settings", response_model=dict)
async def get_tenant_settings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:read")),
    _: None = Depends(require_tenant_access),
) -> dict:
    """获取租户配置（需要 ``tenant:read`` 权限）。"""
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 ID {tenant_id} 不存在",
        )
    return await tenant_service.get_tenant_settings(db, tenant)


@router.put("/{tenant_id}/settings", response_model=TenantResponse)
async def update_tenant_settings(
    tenant_id: int,
    payload: TenantSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:write")),
    _: None = Depends(require_tenant_access),
) -> TenantResponse:
    """更新租户配置（需要 ``tenant:write`` 权限）。"""
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 ID {tenant_id} 不存在",
        )
    updated = await tenant_service.update_tenant_settings(db, tenant, payload)
    return TenantResponse.model_validate(updated)


# ──────────────────────────────────────────────
# 租户成员管理
# ──────────────────────────────────────────────


@router.post(
    "/{tenant_id}/members",
    response_model=TenantMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    tenant_id: int,
    payload: TenantMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:write")),
    _: None = Depends(require_tenant_access),
) -> TenantMemberResponse:
    """添加租户成员（需要 ``tenant:write`` 权限）。"""
    try:
        member = await tenant_service.add_member(db, tenant_id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return TenantMemberResponse.model_validate(member)


@router.get("/{tenant_id}/members", response_model=TenantMemberListResponse)
async def list_members(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:read")),
    _: None = Depends(require_tenant_access),
) -> TenantMemberListResponse:
    """获取租户成员列表（需要 ``tenant:read`` 权限）。"""
    members = await tenant_service.list_members(db, tenant_id)
    total = await tenant_service.count_members(db, tenant_id)
    return TenantMemberListResponse(
        items=[TenantMemberResponse.model_validate(m) for m in members],
        total=total,
    )


@router.put(
    "/{tenant_id}/members/{user_id}",
    response_model=TenantMemberResponse,
)
async def update_member(
    tenant_id: int,
    user_id: int,
    payload: TenantMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:write")),
    _: None = Depends(require_tenant_access),
) -> TenantMemberResponse:
    """更新租户成员角色（需要 ``tenant:write`` 权限）。"""
    member = await tenant_service.get_member(db, tenant_id, user_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 {tenant_id} 中不存在用户 {user_id}",
        )
    updated = await tenant_service.update_member(db, member, payload)
    return TenantMemberResponse.model_validate(updated)


@router.delete(
    "/{tenant_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    tenant_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("tenant:write")),
    _: None = Depends(require_tenant_access),
) -> None:
    """移除租户成员（需要 ``tenant:write`` 权限）。"""
    member = await tenant_service.get_member(db, tenant_id, user_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户 {tenant_id} 中不存在用户 {user_id}",
        )
    await tenant_service.remove_member(db, member)


__all__ = ["router"]
