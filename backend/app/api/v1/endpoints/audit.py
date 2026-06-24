"""审计日志查询端点。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.core.rbac import Permissions
from app.models.user import User
from app.services import audit_service

router = APIRouter()


class AuditLogResponse(BaseModel):
    """审计日志响应。"""

    id: int
    user_id: int | None
    tenant_id: int | None
    action: str
    resource_type: str | None
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """审计日志列表响应（带分页信息）。"""

    items: list[AuditLogResponse]
    total: int
    skip: int
    limit: int


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    user_id: int | None = Query(None, description="按用户 ID 过滤"),
    tenant_id: int | None = Query(None, description="按租户 ID 过滤"),
    action: str | None = Query(None, description="按操作动作过滤"),
    resource_type: str | None = Query(None, description="按资源类型过滤"),
    start_date: datetime | None = Query(None, description="起始时间"),
    end_date: datetime | None = Query(None, description="截止时间"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.AUDIT_READ)),
) -> AuditLogListResponse:
    """查询审计日志（需要 ``audit:read`` 权限）。"""
    filters: dict[str, Any] = {}
    if user_id is not None:
        filters["user_id"] = user_id
    if tenant_id is not None:
        filters["tenant_id"] = tenant_id
    if action:
        filters["action"] = action
    if resource_type:
        filters["resource_type"] = resource_type
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date

    logs = await audit_service.get_audit_logs(db, filters=filters, skip=skip, limit=limit)
    total = await audit_service.count_audit_logs(db, filters=filters)

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit,
    )


def _build_filters(
    user_id: int | None,
    tenant_id: int | None,
    action: str | None,
    resource_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> dict[str, Any]:
    """构建审计日志过滤条件字典。"""
    filters: dict[str, Any] = {}
    if user_id is not None:
        filters["user_id"] = user_id
    if tenant_id is not None:
        filters["tenant_id"] = tenant_id
    if action:
        filters["action"] = action
    if resource_type:
        filters["resource_type"] = resource_type
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date
    return filters


@router.get("/export")
async def export_audit_logs_csv(
    user_id: int | None = Query(None, description="按用户 ID 过滤"),
    tenant_id: int | None = Query(None, description="按租户 ID 过滤"),
    action: str | None = Query(None, description="按操作动作过滤"),
    resource_type: str | None = Query(None, description="按资源类型过滤"),
    start_date: datetime | None = Query(None, description="起始时间"),
    end_date: datetime | None = Query(None, description="截止时间"),
    limit: int = Query(10000, ge=1, le=100000, description="导出记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.AUDIT_READ)),
) -> Response:
    """导出审计日志为 CSV 文件（需要 ``audit:read`` 权限）。

    支持与列表查询相同的过滤条件，导出量通过 ``limit`` 限制。
    """
    filters = _build_filters(
        user_id, tenant_id, action, resource_type, start_date, end_date
    )
    content = await audit_service.export_audit_logs(
        db, filters=filters, format="csv", limit=limit
    )
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit_logs_{timestamp}.csv"'
            ),
        },
    )


@router.get("/export-json")
async def export_audit_logs_json(
    user_id: int | None = Query(None, description="按用户 ID 过滤"),
    tenant_id: int | None = Query(None, description="按租户 ID 过滤"),
    action: str | None = Query(None, description="按操作动作过滤"),
    resource_type: str | None = Query(None, description="按资源类型过滤"),
    start_date: datetime | None = Query(None, description="起始时间"),
    end_date: datetime | None = Query(None, description="截止时间"),
    limit: int = Query(10000, ge=1, le=100000, description="导出记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.AUDIT_READ)),
) -> Response:
    """导出审计日志为 JSON 文件（需要 ``audit:read`` 权限）。

    支持与列表查询相同的过滤条件，导出量通过 ``limit`` 限制。
    """
    filters = _build_filters(
        user_id, tenant_id, action, resource_type, start_date, end_date
    )
    content = await audit_service.export_audit_logs(
        db, filters=filters, format="json", limit=limit
    )
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit_logs_{timestamp}.json"'
            ),
        },
    )
