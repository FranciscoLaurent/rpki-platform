"""Anycast 节点管理 API 端点。

提供 Anycast 节点的 CRUD 接口。

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
    AnycastNodeCreate,
    AnycastNodeListResponse,
    AnycastNodeResponse,
    AnycastNodeUpdate,
)
from app.services.anycast_service import (
    count_anycast_nodes,
    create_anycast_node,
    delete_anycast_node,
    get_anycast_node,
    get_anycast_nodes,
    update_anycast_node,
)

router = APIRouter()

# 权限码（使用字符串字面量避免修改共享的 rbac.py）
ASSET_WRITE = "asset:write"
ASSET_READ = "asset:read"


@router.post(
    "",
    response_model=AnycastNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_anycast_node_endpoint(
    payload: AnycastNodeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> AnycastNodeResponse:
    """创建 Anycast 节点（需要 ``asset:write`` 权限）。"""
    node = await create_anycast_node(db, payload)
    return AnycastNodeResponse.model_validate(node)


@router.get("", response_model=AnycastNodeListResponse)
async def list_anycast_nodes(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数上限"),
    node_asn: int | None = Query(None, description="按节点 ASN 过滤"),
    prefix: str | None = Query(None, description="按前缀过滤"),
    region: str | None = Query(None, description="按地域过滤"),
    status_filter: str | None = Query(
        None, alias="status", description="按状态过滤"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_READ)),
) -> AnycastNodeListResponse:
    """获取 Anycast 节点列表（需要 ``asset:read`` 权限）。"""
    filters: dict[str, object] = {}
    if node_asn is not None:
        filters["node_asn"] = node_asn
    if prefix is not None:
        filters["prefix"] = prefix
    if region is not None:
        filters["region"] = region
    if status_filter is not None:
        filters["status"] = status_filter

    items = await get_anycast_nodes(db, filters=filters, skip=skip, limit=limit)
    total = await count_anycast_nodes(db, filters=filters)
    return AnycastNodeListResponse(
        items=[AnycastNodeResponse.model_validate(n) for n in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{node_id}",
    response_model=AnycastNodeResponse,
)
async def get_anycast_node_endpoint(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_READ)),
) -> AnycastNodeResponse:
    """获取 Anycast 节点详情（需要 ``asset:read`` 权限）。"""
    node = await get_anycast_node(db, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anycast 节点 ID {node_id} 不存在",
        )
    return AnycastNodeResponse.model_validate(node)


@router.put(
    "/{node_id}",
    response_model=AnycastNodeResponse,
)
async def update_anycast_node_endpoint(
    node_id: int,
    payload: AnycastNodeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> AnycastNodeResponse:
    """更新 Anycast 节点（需要 ``asset:write`` 权限）。"""
    node = await get_anycast_node(db, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anycast 节点 ID {node_id} 不存在",
        )
    updated = await update_anycast_node(db, node, payload)
    return AnycastNodeResponse.model_validate(updated)


@router.delete(
    "/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_anycast_node_endpoint(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> None:
    """删除 Anycast 节点（需要 ``asset:write`` 权限）。"""
    node = await get_anycast_node(db, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anycast 节点 ID {node_id} 不存在",
        )
    await delete_anycast_node(db, node)


__all__ = ["router"]
