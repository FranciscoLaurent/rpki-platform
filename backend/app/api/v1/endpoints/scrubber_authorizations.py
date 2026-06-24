"""清洗商授权管理 API 端点。

提供清洗商授权的 CRUD 接口。

注意：
    本端点模块不通过 ``app.api.v1.router`` 注册（共享文件不可修改），
    使用方需在路由聚合处显式 ``include_router``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.benign_conflict import (
    ScrubberAuthorizationCreate,
    ScrubberAuthorizationListResponse,
    ScrubberAuthorizationResponse,
    ScrubberAuthorizationUpdate,
)
from app.services.scrubber_service import (
    count_scrubber_authorizations,
    create_scrubber_authorization,
    delete_scrubber_authorization,
    get_scrubber_authorization,
    get_scrubber_authorizations,
    update_scrubber_authorization,
)

router = APIRouter()

# 权限码（使用字符串字面量避免修改共享的 rbac.py）
ASSET_WRITE = "asset:write"
ASSET_READ = "asset:read"


@router.post(
    "",
    response_model=ScrubberAuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scrubber_authorization_endpoint(
    payload: ScrubberAuthorizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> ScrubberAuthorizationResponse:
    """创建清洗商授权（需要 ``asset:write`` 权限）。"""
    authorization = await create_scrubber_authorization(db, payload)
    return ScrubberAuthorizationResponse.model_validate(authorization)


@router.get("", response_model=ScrubberAuthorizationListResponse)
async def list_scrubber_authorizations(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数上限"),
    scrubber_asn: int | None = Query(None, description="按清洗商 ASN 过滤"),
    customer_asn: int | None = Query(None, description="按客户 ASN 过滤"),
    customer_prefix: str | None = Query(None, description="按客户前缀过滤"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_READ)),
) -> ScrubberAuthorizationListResponse:
    """获取清洗商授权列表（需要 ``asset:read`` 权限）。"""
    filters: dict[str, object] = {}
    if scrubber_asn is not None:
        filters["scrubber_asn"] = scrubber_asn
    if customer_asn is not None:
        filters["customer_asn"] = customer_asn
    if customer_prefix is not None:
        filters["customer_prefix"] = customer_prefix
    if status_filter is not None:
        filters["status"] = status_filter

    items = await get_scrubber_authorizations(db, filters=filters, skip=skip, limit=limit)
    total = await count_scrubber_authorizations(db, filters=filters)
    return ScrubberAuthorizationListResponse(
        items=[ScrubberAuthorizationResponse.model_validate(a) for a in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{auth_id}",
    response_model=ScrubberAuthorizationResponse,
)
async def get_scrubber_authorization_endpoint(
    auth_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_READ)),
) -> ScrubberAuthorizationResponse:
    """获取清洗商授权详情（需要 ``asset:read`` 权限）。"""
    authorization = await get_scrubber_authorization(db, auth_id)
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"清洗商授权 ID {auth_id} 不存在",
        )
    return ScrubberAuthorizationResponse.model_validate(authorization)


@router.put(
    "/{auth_id}",
    response_model=ScrubberAuthorizationResponse,
)
async def update_scrubber_authorization_endpoint(
    auth_id: int,
    payload: ScrubberAuthorizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> ScrubberAuthorizationResponse:
    """更新清洗商授权（需要 ``asset:write`` 权限）。"""
    authorization = await get_scrubber_authorization(db, auth_id)
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"清洗商授权 ID {auth_id} 不存在",
        )
    updated = await update_scrubber_authorization(db, authorization, payload)
    return ScrubberAuthorizationResponse.model_validate(updated)


@router.delete(
    "/{auth_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_scrubber_authorization_endpoint(
    auth_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> None:
    """删除清洗商授权（需要 ``asset:write`` 权限）。"""
    authorization = await get_scrubber_authorization(db, auth_id)
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"清洗商授权 ID {auth_id} 不存在",
        )
    await delete_scrubber_authorization(db, authorization)


__all__ = ["router"]
