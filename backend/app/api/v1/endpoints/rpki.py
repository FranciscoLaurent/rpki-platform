"""RPKI 仓库同步与对象验证 API 端点。

提供 TAL 管理、仓库同步、ROA/VRP 查询、BGP 公告验证、
快照管理与健康检查等接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.rpki import (
    BatchValidationRequest,
    BatchValidationResponse,
    BGPAnnouncementValidation,
    BGPAnnouncementValidationRequest,
    RPKIHealthResponse,
    RPKIRepositoryListResponse,
    RPKIRepositoryResponse,
    ROAListResponse,
    ROAResponse,
    SnapshotDiffResponse,
    SnapshotListResponse,
    SnapshotResponse,
    SnapshotRollbackResponse,
    SyncStatusResponse,
    SyncTriggerResponse,
    TALCreate,
    TALListResponse,
    TALResponse,
    VRPListResponse,
    VRPResponse,
)
from app.services import rpki_health_service, rpki_sync_service, vrp_service

router = APIRouter()

# RPKI 权限码（与 RBAC 系统约定，使用字符串字面量避免修改共享的 rbac.py）
RPKI_READ = "rpki:read"
RPKI_WRITE = "rpki:write"


# ──────────────────────────────────────────────
# TAL 管理
# ──────────────────────────────────────────────


@router.post("/tals", response_model=TALResponse, status_code=status.HTTP_201_CREATED)
async def create_tal(
    tal_create: TALCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_WRITE)),
) -> TALResponse:
    """创建 TAL（Trust Anchor Locator）。

    需要 ``rpki:write`` 权限。
    """
    tal = await rpki_sync_service.init_tal(db, tal_create)
    return TALResponse.model_validate(tal)


@router.get("/tals", response_model=TALListResponse)
async def list_tals(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> TALListResponse:
    """获取 TAL 列表。

    需要 ``rpki:read`` 权限。
    """
    tals = await rpki_sync_service.list_tals(db, skip=skip, limit=limit)
    total = await rpki_sync_service.count_tals(db)
    return TALListResponse(
        items=[TALResponse.model_validate(t) for t in tals],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/tals/{tal_id}", response_model=TALResponse)
async def get_tal(
    tal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> TALResponse:
    """获取 TAL 详情。

    需要 ``rpki:read`` 权限。
    """
    tal = await rpki_sync_service.get_tal_by_id(db, tal_id)
    if tal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TAL ID {tal_id} 不存在",
        )
    return TALResponse.model_validate(tal)


@router.delete("/tals/{tal_id}", response_model=SyncTriggerResponse)
async def delete_tal(
    tal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_WRITE)),
) -> SyncTriggerResponse:
    """删除（禁用）TAL。

    需要 ``rpki:write`` 权限。采用软删除策略，将 TAL 状态置为 disabled。
    """
    deleted = await rpki_sync_service.delete_tal(db, tal_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TAL ID {tal_id} 不存在",
        )
    return SyncTriggerResponse(
        message=f"TAL {tal_id} 已禁用",
        tal_id=tal_id,
        status="disabled",
    )


@router.post("/tals/{tal_id}/sync", response_model=SyncTriggerResponse)
async def sync_tal(
    tal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_WRITE)),
) -> SyncTriggerResponse:
    """触发指定 TAL 关联仓库的同步。

    需要 ``rpki:write`` 权限。
    """
    tal = await rpki_sync_service.get_tal_by_id(db, tal_id)
    if tal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TAL ID {tal_id} 不存在",
        )

    # 查询该 TAL 下的所有仓库并同步
    repositories = await rpki_sync_service.list_repositories(db, tal_id=tal_id)
    if not repositories:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TAL {tal_id} 下无关联仓库",
        )

    # 同步第一个仓库（占位：实际可并行同步多个）
    repo = repositories[0]
    synced_repo = await rpki_sync_service.sync_repository(db, repo.id)

    return SyncTriggerResponse(
        message=f"TAL {tal_id} 同步完成",
        tal_id=tal_id,
        status=synced_repo.sync_status,
    )


# ──────────────────────────────────────────────
# 仓库同步
# ──────────────────────────────────────────────


@router.post("/sync-all", response_model=SyncTriggerResponse)
async def sync_all_repositories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_WRITE)),
) -> SyncTriggerResponse:
    """同步所有活跃仓库。

    需要 ``rpki:write`` 权限。
    """
    result = await rpki_sync_service.sync_all_repositories(db)
    return SyncTriggerResponse(
        message=(
            f"同步完成：成功 {result['success']}，失败 {result['failed']}"
        ),
        tal_id=None,
        status="success" if result["failed"] == 0 else "partial",
    )


@router.get("/sync-status", response_model=list[SyncStatusResponse])
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> list[SyncStatusResponse]:
    """获取所有仓库同步状态。

    需要 ``rpki:read`` 权限。
    """
    return await rpki_health_service.get_sync_status(db)


# ──────────────────────────────────────────────
# 仓库查询
# ──────────────────────────────────────────────


@router.get("/repositories", response_model=RPKIRepositoryListResponse)
async def list_repositories(
    tal_id: int | None = Query(None, description="按 TAL ID 过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> RPKIRepositoryListResponse:
    """获取仓库列表。

    需要 ``rpki:read`` 权限。
    """
    repositories = await rpki_sync_service.list_repositories(
        db, tal_id=tal_id, skip=skip, limit=limit
    )
    total = await rpki_sync_service.count_repositories(db, tal_id=tal_id)
    return RPKIRepositoryListResponse(
        items=[RPKIRepositoryResponse.model_validate(r) for r in repositories],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/repositories/{repo_id}", response_model=RPKIRepositoryResponse)
async def get_repository(
    repo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> RPKIRepositoryResponse:
    """获取仓库详情。

    需要 ``rpki:read`` 权限。
    """
    repo = await rpki_sync_service.get_repository_by_id(db, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"仓库 ID {repo_id} 不存在",
        )
    return RPKIRepositoryResponse.model_validate(repo)


# ──────────────────────────────────────────────
# ROA 查询
# ──────────────────────────────────────────────


@router.get("/roas", response_model=ROAListResponse)
async def list_roas(
    prefix: str | None = Query(None, description="按前缀过滤"),
    origin_as: int | None = Query(None, description="按起源 AS 过滤"),
    tal_id: int | None = Query(None, description="按 TAL ID 过滤"),
    roa_status: str | None = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> ROAListResponse:
    """查询 ROA 列表。

    需要 ``rpki:read`` 权限。
    """
    roas = await vrp_service.query_roas(
        db,
        prefix=prefix,
        origin_as=origin_as,
        tal_id=tal_id,
        status=roa_status,
        skip=skip,
        limit=limit,
    )
    total = await vrp_service.count_roas(
        db,
        prefix=prefix,
        origin_as=origin_as,
        tal_id=tal_id,
        status=roa_status,
    )
    return ROAListResponse(
        items=[ROAResponse.model_validate(r) for r in roas],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/roas/{roa_id}", response_model=ROAResponse)
async def get_roa(
    roa_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> ROAResponse:
    """获取 ROA 详情。

    需要 ``rpki:read`` 权限。
    """
    roa = await vrp_service.get_roa_by_id(db, roa_id)
    if roa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ROA ID {roa_id} 不存在",
        )
    return ROAResponse.model_validate(roa)


# ──────────────────────────────────────────────
# VRP 查询
# ──────────────────────────────────────────────


@router.get("/vrps", response_model=VRPListResponse)
async def list_vrps(
    prefix: str | None = Query(None, description="按前缀过滤（返回覆盖该前缀的 VRP）"),
    origin_as: int | None = Query(None, description="按起源 AS 过滤"),
    max_length: int | None = Query(None, description="按最大前缀长度过滤"),
    tal_id: int | None = Query(None, description="按 TAL ID 过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> VRPListResponse:
    """查询 VRP 列表。

    需要 ``rpki:read`` 权限。前缀过滤会返回所有覆盖该前缀的 VRP。
    """
    vrps = await vrp_service.query_vrps(
        db,
        prefix=prefix,
        origin_as=origin_as,
        max_length=max_length,
        tal_id=tal_id,
        skip=skip,
        limit=limit,
    )
    total = await vrp_service.count_vrps(
        db,
        prefix=prefix,
        origin_as=origin_as,
        max_length=max_length,
        tal_id=tal_id,
    )
    return VRPListResponse(
        items=[VRPResponse.model_validate(v) for v in vrps],
        total=total,
        skip=skip,
        limit=limit,
    )


# ──────────────────────────────────────────────
# BGP 公告验证
# ──────────────────────────────────────────────


@router.post("/validate", response_model=BGPAnnouncementValidation)
async def validate_bgp_announcement(
    request: BGPAnnouncementValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> BGPAnnouncementValidation:
    """验证单个 BGP 公告。

    需要 ``rpki:read`` 权限。返回 Valid/Invalid/NotFound 及 Invalid 原因。
    """
    return await vrp_service.validate_bgp_announcement(
        db, request.prefix, request.origin_as
    )


@router.post("/validate-batch", response_model=BatchValidationResponse)
async def validate_bgp_announcements_batch(
    request: BatchValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> BatchValidationResponse:
    """批量验证 BGP 公告。

    需要 ``rpki:read`` 权限。
    """
    results = await vrp_service.validate_bgp_announcements(db, request.announcements)

    valid_count = sum(
        1 for r in results if r.validation_result
        and r.validation_result.validation_status == "valid"
    )
    invalid_count = sum(
        1 for r in results if r.validation_result
        and r.validation_result.validation_status == "invalid"
    )
    not_found_count = sum(
        1 for r in results if r.validation_result
        and r.validation_result.validation_status == "not_found"
    )

    return BatchValidationResponse(
        results=results,
        total=len(results),
        valid_count=valid_count,
        invalid_count=invalid_count,
        not_found_count=not_found_count,
    )


# ──────────────────────────────────────────────
# 健康检查
# ──────────────────────────────────────────────


@router.get("/health", response_model=RPKIHealthResponse)
async def get_rpki_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> RPKIHealthResponse:
    """获取 RPKI 整体健康状态。

    需要 ``rpki:read`` 权限。
    """
    return await rpki_health_service.get_overall_health(db)


# ──────────────────────────────────────────────
# 快照管理
# ──────────────────────────────────────────────


@router.post(
    "/snapshots",
    response_model=SnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_WRITE)),
) -> SnapshotResponse:
    """创建 RPKI 数据快照。

    需要 ``rpki:write`` 权限。
    """
    snapshot = await vrp_service.create_snapshot(db)
    return SnapshotResponse.model_validate(snapshot)


@router.get("/snapshots", response_model=SnapshotListResponse)
async def list_snapshots(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> SnapshotListResponse:
    """获取快照列表。

    需要 ``rpki:read`` 权限。
    """
    snapshots = await vrp_service.list_snapshots(db, skip=skip, limit=limit)
    total = await vrp_service.count_snapshots(db)
    return SnapshotListResponse(
        items=[SnapshotResponse.model_validate(s) for s in snapshots],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/snapshots/{snapshot_id}/diff", response_model=SnapshotDiffResponse)
async def get_snapshot_diff(
    snapshot_id: int,
    snapshot_id_2: int = Query(..., description="对比的另一个快照 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_READ)),
) -> SnapshotDiffResponse:
    """获取快照差异。

    需要 ``rpki:read`` 权限。对比当前快照与参数指定的另一个快照。
    """
    try:
        return await vrp_service.get_snapshot_diff(db, snapshot_id, snapshot_id_2)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/snapshots/{snapshot_id}/rollback",
    response_model=SnapshotRollbackResponse,
)
async def rollback_to_snapshot(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RPKI_WRITE)),
) -> SnapshotRollbackResponse:
    """回滚到指定快照。

    需要 ``rpki:write`` 权限。
    """
    try:
        return await vrp_service.rollback_to_snapshot(db, snapshot_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
