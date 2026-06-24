"""驾驶舱与详情视图 API 端点。

提供总览驾驶舱、前缀详情、ASN 详情与事件时间线查询接口。
所有接口均需要认证，使用 ``prefix:read``、``bgp:read``、``detection:read``
等已有权限码组合校验。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import (
    ASNDetail,
    DashboardOverview,
    IncidentTimeline,
    PrefixDetail,
)
from app.services import dashboard_service

router = APIRouter()

# 驾驶舱权限码：复用已有权限，至少需要查看 BGP 或前缀的权限
DASHBOARD_READ_PERMS = ("bgp:read", "prefix:read", "detection:read")


@router.get("/overview", response_model=DashboardOverview)
async def get_dashboard_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(*DASHBOARD_READ_PERMS)),
) -> DashboardOverview:
    """获取总览驾驶舱数据（需要 ``bgp:read``/``prefix:read``/``detection:read`` 权限之一）。

    返回企业 IP/ASN 数量、ROA 覆盖率、Valid/Invalid/NotFound 分布、
    P0/P1 事件数量、RPKI cache 状态、BGP 数据源状态与最近 7 天风险趋势。
    """
    return await dashboard_service.get_dashboard_overview(db)


@router.get("/prefixes/{prefix_id}/detail", response_model=PrefixDetail)
async def get_prefix_detail(
    prefix_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:read")),
) -> PrefixDetail:
    """获取前缀详情（需要 ``prefix:read`` 权限）。

    返回前缀资产属性、合法 origin、当前公告、AS_PATH、ROA/VRP 命中、
    IRR 信息（占位）、历史状态（占位）、告警、业务影响与操作建议。
    """
    detail = await dashboard_service.get_prefix_detail(db, prefix_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    return detail


@router.get("/asns/{asn_id}/detail", response_model=ASNDetail)
async def get_asn_detail(
    asn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("prefix:read", "bgp:read")),
) -> ASNDetail:
    """获取 ASN 详情（需要 ``prefix:read`` 或 ``bgp:read`` 权限）。

    返回 ASN 基本信息、关联前缀、上下游/对等关系（占位）、
    历史路径（占位）、异常记录与风险画像。
    """
    detail = await dashboard_service.get_asn_detail(db, asn_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ASN ID {asn_id} 不存在",
        )
    return detail


@router.get("/incidents/{incident_id}/timeline", response_model=IncidentTimeline)
async def get_incident_timeline(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("detection:read")),
) -> IncidentTimeline:
    """获取事件时间线（需要 ``detection:read`` 权限）。

    返回事件基本信息、按时间排序的时间线（首次出现、传播变化、告警、
    人工确认、处置、恢复、关闭）、关联告警、影响范围与处置建议。
    """
    timeline = await dashboard_service.get_incident_timeline(db, incident_id)
    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )
    return timeline
