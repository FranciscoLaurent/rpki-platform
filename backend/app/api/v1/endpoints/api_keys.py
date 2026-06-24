"""API Key 管理 API 端点。

提供 API Key 的创建、查询、更新与删除接口。
明文密钥仅在创建时返回一次，后续仅展示密钥前缀。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
)
from app.services import api_key_service

router = APIRouter()

# API Key 管理权限码
API_KEY_MANAGE = "api_key:manage"


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(API_KEY_MANAGE)),
) -> ApiKeyCreateResponse:
    """创建 API Key（需要 ``api_key:manage`` 权限）。

    生成新的 API Key，明文密钥仅在此次响应中返回，请妥善保存。
    """
    api_key, plaintext = await api_key_service.create_api_key(
        db,
        user_id=current_user.id,
        name=payload.name,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        tenant_id=current_user.tenant_id,
    )
    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=plaintext,
        key_prefix=api_key.key_prefix,
        user_id=api_key.user_id,
        tenant_id=api_key.tenant_id,
        scopes=api_key.scopes or [],
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    is_active: bool | None = Query(None, description="按启用状态过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(API_KEY_MANAGE)),
) -> ApiKeyListResponse:
    """获取 API Key 列表（需要 ``api_key:manage`` 权限）。"""
    keys = await api_key_service.list_api_keys(
        db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    total = await api_key_service.count_api_keys(
        db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        is_active=is_active,
    )
    return ApiKeyListResponse(
        items=[ApiKeyResponse.model_validate(k) for k in keys],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{api_key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    api_key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(API_KEY_MANAGE)),
) -> ApiKeyResponse:
    """获取 API Key 详情（需要 ``api_key:manage`` 权限）。"""
    api_key = await api_key_service.get_api_key(db, api_key_id)
    if api_key is None or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Key ID {api_key_id} 不存在",
        )
    return ApiKeyResponse.model_validate(api_key)


@router.put("/{api_key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    api_key_id: int,
    payload: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(API_KEY_MANAGE)),
) -> ApiKeyResponse:
    """更新 API Key（需要 ``api_key:manage`` 权限）。"""
    api_key = await api_key_service.get_api_key(db, api_key_id)
    if api_key is None or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Key ID {api_key_id} 不存在",
        )
    updated = await api_key_service.update_api_key(
        db,
        api_key,
        name=payload.name,
        scopes=payload.scopes,
        is_active=payload.is_active,
        expires_at=payload.expires_at,
    )
    return ApiKeyResponse.model_validate(updated)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_api_key(
    api_key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(API_KEY_MANAGE)),
) -> None:
    """删除 API Key（需要 ``api_key:manage`` 权限）。"""
    api_key = await api_key_service.get_api_key(db, api_key_id)
    if api_key is None or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API Key ID {api_key_id} 不存在",
        )
    await api_key_service.delete_api_key(db, api_key_id)


__all__ = ["router"]
