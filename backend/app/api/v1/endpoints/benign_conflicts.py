"""ROA 良性冲突管理 API 端点。

提供良性冲突记录查询、状态更新、手动分析与统计摘要接口。

注意：
    本端点模块不通过 ``app.api.v1.router`` 注册（共享文件不可修改），
    使用方需在路由聚合处显式 ``include_router``。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.detection import Alert
from app.models.user import User
from app.schemas.benign_conflict import (
    BenignConflictAnalysisResult,
    BenignConflictAnalyzeRequest,
    BenignConflictQueryParams,
    BenignConflictRecordListResponse,
    BenignConflictRecordResponse,
    BenignConflictStatusUpdate,
    BenignConflictSummary,
)
from app.services import alert_service
from app.services.benign_conflict import BenignConflictDetector
from app.services.benign_conflict_service import (
    count_benign_conflict_records,
    get_benign_conflict_record,
    get_benign_conflict_records,
    get_benign_conflict_summary,
    update_benign_conflict_status,
)

router = APIRouter()

# 权限码（使用字符串字面量避免修改共享的 rbac.py）
DETECTION_READ = "detection:read"
DETECTION_WRITE = "detection:write"


@router.get(
    "",
    response_model=BenignConflictRecordListResponse,
)
async def list_benign_conflicts(
    prefix: str | None = Query(None, description="按前缀过滤"),
    origin_as: int | None = Query(None, description="按起源 AS 过滤"),
    conflict_type: str | None = Query(None, description="按冲突类型过滤"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    start_time: datetime | None = Query(None, description="起始时间"),
    end_time: datetime | None = Query(None, description="截止时间"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> BenignConflictRecordListResponse:
    """查询良性冲突记录列表（需要 ``detection:read`` 权限）。"""
    query_params = BenignConflictQueryParams(
        prefix=prefix,
        origin_as=origin_as,
        conflict_type=conflict_type,
        status=status_filter,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )
    items = await get_benign_conflict_records(db, query_params, skip, limit)
    total = await count_benign_conflict_records(db, query_params)
    return BenignConflictRecordListResponse(
        items=[BenignConflictRecordResponse.model_validate(r) for r in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/summary",
    response_model=BenignConflictSummary,
)
async def get_benign_conflict_summary_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> BenignConflictSummary:
    """获取良性冲突统计摘要（需要 ``detection:read`` 权限）。"""
    return await get_benign_conflict_summary(db)


@router.get(
    "/{record_id}",
    response_model=BenignConflictRecordResponse,
)
async def get_benign_conflict(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> BenignConflictRecordResponse:
    """获取良性冲突记录详情（需要 ``detection:read`` 权限）。"""
    record = await get_benign_conflict_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"良性冲突记录 ID {record_id} 不存在",
        )
    return BenignConflictRecordResponse.model_validate(record)


@router.put(
    "/{record_id}/status",
    response_model=BenignConflictRecordResponse,
)
async def update_benign_conflict_record_status(
    record_id: int,
    status_update: BenignConflictStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> BenignConflictRecordResponse:
    """更新良性冲突记录状态（需要 ``detection:write`` 权限）。"""
    record = await get_benign_conflict_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"良性冲突记录 ID {record_id} 不存在",
        )
    updated = await update_benign_conflict_status(
        db,
        record,
        status_update.status,
        recommendation=status_update.recommendation,
        related_work_order=status_update.related_work_order,
    )
    return BenignConflictRecordResponse.model_validate(updated)


@router.post(
    "/analyze",
    response_model=BenignConflictAnalysisResult,
)
async def analyze_benign_conflict(
    request: BenignConflictAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> BenignConflictAnalysisResult:
    """手动分析告警是否为良性冲突（需要 ``detection:read`` 权限）。

    输入：
    - ``alert_id``：分析指定告警
    - ``prefix`` + ``origin_as``：分析指定前缀与起源 AS

    返回良性冲突分析结果，包含冲突类型、置信度、证据与处理建议。

    重要：良性冲突识别只降低误报优先级，不能替代安全验证。
    """
    alert: Alert | None = None

    if request.alert_id is not None:
        # 通过 alert_id 获取告警
        alert = await alert_service.get_alert(db, request.alert_id)
        if alert is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"告警 ID {request.alert_id} 不存在",
            )
    else:
        # 通过 prefix + origin_as 构造临时告警对象（不持久化）
        if request.prefix is None or request.origin_as is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="必须提供 alert_id，或同时提供 prefix 与 origin_as",
            )
        alert = Alert(
            prefix=request.prefix,
            origin_as=request.origin_as,
            alert_type="manual_analysis",
            severity="P3",
            title=f"手动分析：{request.prefix} AS{request.origin_as}",
            description="手动触发的良性冲突分析",
        )

    # 执行良性冲突分析
    detector = BenignConflictDetector()
    result = await detector.analyze(db, alert)
    return result


__all__ = ["router"]
