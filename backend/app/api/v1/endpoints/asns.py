"""ASN 管理端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.asn import (
    ASNCreate,
    ASNListResponse,
    ASNResponse,
    ASNUpdate,
)
from app.services import asn_service

router = APIRouter()


@router.post(
    "",
    response_model=ASNResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asn(
    payload: ASNCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asn:write")),
) -> ASNResponse:
    """创建 ASN（需要 ``asn:write`` 权限）。"""
    try:
        asn = await asn_service.create_asn(db, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return ASNResponse.model_validate(asn)


@router.get("", response_model=ASNListResponse)
async def list_asns(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    asn: int | None = Query(None, description="按 ASN 号过滤"),
    name: str | None = Query(None, description="按名称模糊过滤"),
    asn_type: str | None = Query(None, description="按 AS 关系类型过滤"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asn:read")),
) -> ASNListResponse:
    """获取 ASN 列表（需要 ``asn:read`` 权限）。"""
    filters: dict[str, object] = {}
    if asn is not None:
        filters["asn"] = asn
    if name is not None:
        filters["name"] = name
    if asn_type is not None:
        filters["asn_type"] = asn_type
    if status_filter is not None:
        filters["status"] = status_filter

    items = await asn_service.get_asns(db, filters=filters, skip=skip, limit=limit)
    total = await asn_service.count_asns(db, filters=filters)
    return ASNListResponse(
        items=[ASNResponse.model_validate(a) for a in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{asn_id}", response_model=ASNResponse)
async def get_asn(
    asn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asn:read")),
) -> ASNResponse:
    """获取 ASN 详情（需要 ``asn:read`` 权限）。"""
    asn = await asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ASN ID {asn_id} 不存在",
        )
    return ASNResponse.model_validate(asn)


@router.put("/{asn_id}", response_model=ASNResponse)
async def update_asn(
    asn_id: int,
    payload: ASNUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asn:write")),
) -> ASNResponse:
    """更新 ASN（需要 ``asn:write`` 权限）。"""
    asn = await asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ASN ID {asn_id} 不存在",
        )
    updated = await asn_service.update_asn(db, asn, payload)
    return ASNResponse.model_validate(updated)


@router.delete("/{asn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asn(
    asn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asn:write")),
) -> None:
    """删除 ASN（需要 ``asn:write`` 权限）。"""
    asn = await asn_service.get_asn(db, asn_id)
    if asn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ASN ID {asn_id} 不存在",
        )
    await asn_service.delete_asn(db, asn)
