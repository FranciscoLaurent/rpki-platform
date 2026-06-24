"""维护窗口管理 API 端点。

提供维护窗口的 CRUD 接口。

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
    MaintenanceWindowCreate,
    MaintenanceWindowListResponse,
    MaintenanceWindowResponse,
    MaintenanceWindowUpdate,
)
from app.services.maintenance_service import (
    count_maintenance_windows,
    create_maintenance_window,
    delete_maintenance_window,
    get_maintenance_window,
    get_maintenance_windows,
    update_maintenance_window,
)

router = APIRouter()

# 权限码（使用字符串字面量避免修改共享的 rbac.py）
ASSET_WRITE = "asset:write"
ASSET_READ = "asset:read"


@router.post(
    "",
    response_model=MaintenanceWindowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_window_endpoint(
    payload: MaintenanceWindowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> MaintenanceWindowResponse:
    """创建维护窗口（需要 ``asset:write`` 权限）。"""
    window = await create_maintenance_window(db, payload)
    return MaintenanceWindowResponse.model_validate(window)


@router.get("", response_model=MaintenanceWindowListResponse)
async def list_maintenance_windows(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数上限"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    work_order_id: str | None = Query(None, description="按工单号过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_READ)),
) -> MaintenanceWindowListResponse:
    """获取维护窗口列表（需要 ``asset:read`` 权限）。"""
    filters: dict[str, object] = {}
    if status_filter is not None:
        filters["status"] = status_filter
    if work_order_id is not None:
        filters["work_order_id"] = work_order_id

    items = await get_maintenance_windows(db, filters=filters, skip=skip, limit=limit)
    total = await count_maintenance_windows(db, filters=filters)
    return MaintenanceWindowListResponse(
        items=[MaintenanceWindowResponse.model_validate(w) for w in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{window_id}",
    response_model=MaintenanceWindowResponse,
)
async def get_maintenance_window_endpoint(
    window_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_READ)),
) -> MaintenanceWindowResponse:
    """获取维护窗口详情（需要 ``asset:read`` 权限）。"""
    window = await get_maintenance_window(db, window_id)
    if window is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"维护窗口 ID {window_id} 不存在",
        )
    return MaintenanceWindowResponse.model_validate(window)


@router.put(
    "/{window_id}",
    response_model=MaintenanceWindowResponse,
)
async def update_maintenance_window_endpoint(
    window_id: int,
    payload: MaintenanceWindowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> MaintenanceWindowResponse:
    """更新维护窗口（需要 ``asset:write`` 权限）。"""
    window = await get_maintenance_window(db, window_id)
    if window is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"维护窗口 ID {window_id} 不存在",
        )
    updated = await update_maintenance_window(db, window, payload)
    return MaintenanceWindowResponse.model_validate(updated)


@router.delete(
    "/{window_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_maintenance_window_endpoint(
    window_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSET_WRITE)),
) -> None:
    """删除维护窗口（需要 ``asset:write`` 权限）。"""
    window = await get_maintenance_window(db, window_id)
    if window is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"维护窗口 ID {window_id} 不存在",
        )
    await delete_maintenance_window(db, window)


__all__ = ["router"]
