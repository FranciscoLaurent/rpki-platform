"""IP 前缀管理端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.prefix import (
    PrefixBatchImport,
    PrefixBatchImportResult,
    PrefixCreate,
    PrefixListResponse,
    PrefixResponse,
    PrefixTreeNode,
    PrefixUpdate,
)
from app.services import asset_service, prefix_service

router = APIRouter()


@router.post(
    "",
    response_model=PrefixResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prefix(
    payload: PrefixCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:write")),
) -> PrefixResponse:
    """创建前缀（需要 ``prefix:write`` 权限）。

    自动从 CIDR 解析协议族与前缀长度，并查找父前缀建立层级关系。
    """
    try:
        prefix = await prefix_service.create_prefix(db, payload, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return PrefixResponse.model_validate(prefix)


@router.get("", response_model=PrefixListResponse)
async def list_prefixes(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    family: int | None = Query(None, description="按协议族过滤：4 或 6"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    importance: str | None = Query(None, description="按重要度过滤"),
    region: str | None = Query(None, description="按地域过滤"),
    site: str | None = Query(None, description="按机房过滤"),
    cloud_zone: str | None = Query(None, description="按云区域过滤"),
    customer_id: int | None = Query(None, description="按客户 ID 过滤"),
    business_service: str | None = Query(None, description="按业务归属过滤"),
    tag: str | None = Query(None, description="按标签过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:read")),
) -> PrefixListResponse:
    """获取前缀列表（需要 ``prefix:read`` 权限）。"""
    filters: dict[str, object] = {}
    if family is not None:
        filters["family"] = family
    if status_filter is not None:
        filters["status"] = status_filter
    if importance is not None:
        filters["importance"] = importance
    if region is not None:
        filters["region"] = region
    if site is not None:
        filters["site"] = site
    if cloud_zone is not None:
        filters["cloud_zone"] = cloud_zone
    if customer_id is not None:
        filters["customer_id"] = customer_id
    if business_service is not None:
        filters["business_service"] = business_service
    if tag is not None:
        filters["tag"] = tag

    items = await prefix_service.get_prefixes(db, filters=filters, skip=skip, limit=limit)
    total = await prefix_service.count_prefixes(db, filters=filters)
    return PrefixListResponse(
        items=[PrefixResponse.model_validate(p) for p in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/tree", response_model=list[PrefixTreeNode])
async def get_prefix_tree(
    root_id: int | None = Query(None, description="指定根节点 ID，为空则返回所有顶层前缀"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:read")),
) -> list[PrefixTreeNode]:
    """获取前缀树（需要 ``prefix:read`` 权限）。"""
    roots = await prefix_service.get_prefix_tree(db, root_id=root_id)
    return [PrefixTreeNode.model_validate(p) for p in roots]


@router.post(
    "/batch-import",
    response_model=PrefixBatchImportResult,
)
async def batch_import_prefixes(
    payload: PrefixBatchImport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:write")),
) -> PrefixBatchImportResult:
    """批量导入前缀（需要 ``prefix:write`` 权限）。

    逐条创建，单条失败不影响其他项。
    """
    return await prefix_service.batch_import_prefixes(db, payload.prefixes, current_user)


@router.get("/{prefix_id}", response_model=PrefixResponse)
async def get_prefix(
    prefix_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:read")),
) -> PrefixResponse:
    """获取前缀详情（需要 ``prefix:read`` 权限）。"""
    prefix = await prefix_service.get_prefix(db, prefix_id)
    if prefix is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    return PrefixResponse.model_validate(prefix)


@router.put("/{prefix_id}", response_model=PrefixResponse)
async def update_prefix(
    prefix_id: int,
    payload: PrefixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:write")),
) -> PrefixResponse:
    """更新前缀（需要 ``prefix:write`` 权限）。"""
    prefix = await prefix_service.get_prefix(db, prefix_id)
    if prefix is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    try:
        updated = await prefix_service.update_prefix(db, prefix, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return PrefixResponse.model_validate(updated)


@router.delete("/{prefix_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prefix(
    prefix_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:write")),
) -> None:
    """删除前缀（需要 ``prefix:write`` 权限）。

    子前缀的 parent_id 将自动置空。
    """
    prefix = await prefix_service.get_prefix(db, prefix_id)
    if prefix is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    await prefix_service.delete_prefix(db, prefix)


@router.get("/{prefix_id}/relationships")
async def get_prefix_relationships(
    prefix_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:read")),
):
    """获取前缀的关系视图（需要 ``prefix:read`` 权限）。

    返回前缀—ASN—ROA—BGP—业务—事件关联信息。
    """
    prefix = await prefix_service.get_prefix(db, prefix_id)
    if prefix is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    view = await asset_service.get_relationship_view(db, prefix_id)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    return view
