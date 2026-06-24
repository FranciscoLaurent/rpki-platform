"""ROA 生命周期管理 API 端点。

提供 ROA 查询、详情、缺失检测、冲突检测、maxLength 风险检查、
ROA 创建建议、变更影响评估、覆盖率统计与健康度摘要等接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.core.rbac import Permissions
from app.models.user import User
from app.schemas.bgp import BGPAnnouncementResponse
from app.schemas.roa import (
    MaxLengthRiskResult,
    ROAChangeImpact,
    ROAChangeParams,
    ROAConflictCheckResult,
    ROACoverageStats,
    ROACreationSuggestion,
    ROADetailResponse,
    ROAHealthSummary,
    ROAListResponse,
    ROAMissingCheckResult,
    ROAQueryParams,
)
from app.schemas.rpki import ROAResponse, VRPResponse
from app.services import roa_service, roa_validation_service

router = APIRouter()


# ──────────────────────────────────────────────
# ROA 查询
# ──────────────────────────────────────────────


@router.get("", response_model=ROAListResponse)
async def list_roas(
    prefix: str | None = Query(None, description="按前缀过滤（精确匹配）"),
    origin_as: int | None = Query(None, description="按起源 AS 过滤"),
    max_length: int | None = Query(None, description="按最大前缀长度过滤"),
    roa_status: str | None = Query(
        None, alias="status", description="按 ROA 状态过滤：valid/expired/revoked"
    ),
    tal_id: int | None = Query(None, description="按 TAL ID 过滤"),
    page: int = Query(1, ge=1, description="页码（从 1 开始）"),
    page_size: int = Query(50, ge=1, le=200, description="每页记录数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> ROAListResponse:
    """查询 ROA 列表。

    需要 ``roa:read`` 权限。支持按 prefix、origin_as、max_length、status、
    tal_id 过滤，支持分页。
    """
    query_params = ROAQueryParams(
        prefix=prefix,
        origin_as=origin_as,
        max_length=max_length,
        status=roa_status,
        tal_id=tal_id,
        page=page,
        page_size=page_size,
    )
    roas, total = await roa_service.get_roas(db, query_params)
    return ROAListResponse(
        items=[ROAResponse.model_validate(r) for r in roas],
        total=total,
        page=page,
        page_size=page_size,
    )


# ──────────────────────────────────────────────
# 静态路径端点（必须在 /{roa_id} 之前定义）
# ──────────────────────────────────────────────


@router.get("/by-prefix", response_model=list[ROAResponse])
async def get_roas_by_prefix(
    prefix: str = Query(..., description="网络前缀"),
    origin_as: int = Query(..., description="起源 AS 号"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> list[ROAResponse]:
    """按前缀和 origin AS 查询 ROA。

    需要 ``roa:read`` 权限。返回匹配 (prefix, origin_as) 的 ROA 列表。
    """
    roas = await roa_service.get_roa_by_prefix_origin(db, prefix, origin_as)
    return [ROAResponse.model_validate(r) for r in roas]


@router.get("/missing-check", response_model=list[ROAMissingCheckResult])
async def check_roa_missing(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> list[ROAMissingCheckResult]:
    """ROA 缺失检测。

    需要 ``roa:read`` 权限。返回已公告但无 ROA 覆盖的前缀列表。
    """
    return await roa_service.check_roa_missing(db)


@router.get("/conflict-check", response_model=list[ROAConflictCheckResult])
async def check_roa_conflict(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> list[ROAConflictCheckResult]:
    """ROA 冲突检测。

    需要 ``roa:read`` 权限。返回存在冲突的 ROA 列表。
    """
    return await roa_service.check_roa_conflict(db)


@router.get(
    "/creation-suggestions",
    response_model=list[ROACreationSuggestion],
)
async def get_roa_creation_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> list[ROACreationSuggestion]:
    """获取 ROA 创建建议。

    需要 ``roa:read`` 权限。返回基于 minimal ROA 原则的创建建议列表。
    """
    return await roa_service.generate_roa_creation_suggestions(db)


@router.get("/coverage-stats", response_model=ROACoverageStats)
async def get_roa_coverage_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> ROACoverageStats:
    """ROA 覆盖率统计。

    需要 ``roa:read`` 权限。返回总前缀数、覆盖率、按重要度与验证状态
    分组的统计信息。
    """
    return await roa_validation_service.get_roa_coverage_stats(db)


@router.get("/health-summary", response_model=ROAHealthSummary)
async def get_roa_health_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> ROAHealthSummary:
    """ROA 健康度摘要。

    需要 ``roa:read`` 权限。返回 ROA 状态分布、覆盖率、缺失数、冲突数
    与高风险数等健康度指标。
    """
    return await roa_validation_service.get_roa_health_summary(db)


# ──────────────────────────────────────────────
# 动态路径端点
# ──────────────────────────────────────────────


@router.get("/{roa_id}", response_model=ROADetailResponse)
async def get_roa_detail(
    roa_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> ROADetailResponse:
    """获取 ROA 详情（含关联 BGP 公告和 VRP）。

    需要 ``roa:read`` 权限。
    """
    roa = await roa_service.get_roa_detail(db, roa_id)
    if roa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ROA ID {roa_id} 不存在",
        )

    # 获取关联的 BGP 公告
    bgp_announcements = await roa_service.get_related_bgp_announcements(db, roa)

    return ROADetailResponse(
        **ROAResponse.model_validate(roa).model_dump(),
        bgp_announcements=[BGPAnnouncementResponse.model_validate(a) for a in bgp_announcements],
        vrps=[VRPResponse.model_validate(v) for v in roa.vrps],
    )


@router.get(
    "/{roa_id}/max-length-risk",
    response_model=MaxLengthRiskResult,
)
async def check_max_length_risk(
    roa_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> MaxLengthRiskResult:
    """maxLength 风险检查。

    需要 ``roa:read`` 权限。返回风险等级、风险因素、劫持面与精确化建议。
    """
    result = await roa_service.check_max_length_risk(db, roa_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ROA ID {roa_id} 不存在",
        )
    return result


@router.post(
    "/{roa_id}/change-impact",
    response_model=ROAChangeImpact,
)
async def assess_roa_change_impact(
    roa_id: int,
    change_params: ROAChangeParams,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.ROA_READ)),
) -> ROAChangeImpact:
    """ROA 变更影响评估。

    需要 ``roa:read`` 权限。输入变更参数，返回受影响的 BGP 公告、业务、
    客户与验证状态变化，并识别高风险变更。
    """
    result = await roa_service.assess_roa_change_impact(db, roa_id, change_params)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ROA ID {roa_id} 不存在",
        )
    return result
