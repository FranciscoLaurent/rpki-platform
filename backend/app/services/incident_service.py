"""事件服务。

提供事件的创建、查询、更新、分派、升级、关闭与时间线管理能力。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import Alert, Incident
from app.schemas.detection import (
    IncidentCreate,
    IncidentQueryParams,
    IncidentUpdate,
    TimelineEvent,
)

logger = get_logger("app.incident_service")


# 严重等级顺序（数值越小越严重）
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


async def create_incident(
    db: AsyncSession, incident_create: IncidentCreate
) -> Incident:
    """创建事件。

    Args:
        db: 异步数据库会话
        incident_create: 事件创建请求

    Returns:
        创建的事件对象（已持久化）
    """
    now = datetime.now(timezone.utc)
    incident = Incident(
        title=incident_create.title,
        description=incident_create.description,
        severity=incident_create.severity,
        status="open",
        alert_ids=incident_create.alert_ids,
        affected_prefixes=incident_create.affected_prefixes,
        affected_asns=incident_create.affected_asns,
        timeline=[
            {
                "timestamp": now.isoformat(),
                "event_type": "created",
                "description": "事件创建",
                "operator": None,
            }
        ],
        first_seen_at=now,
        last_seen_at=now,
        tenant_id=incident_create.tenant_id,
    )
    db.add(incident)
    await db.flush()

    # 若指定了 alert_ids，关联告警
    if incident_create.alert_ids:
        await _link_alerts_to_incident(db, incident_create.alert_ids, incident.id)

    logger.info(
        "事件已创建",
        incident_id=incident.id,
        title=incident.title,
    )
    return incident


async def get_incident(db: AsyncSession, incident_id: int) -> Incident | None:
    """根据 ID 获取事件。"""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_incidents(
    db: AsyncSession,
    filters: IncidentQueryParams,
    skip: int = 0,
    limit: int = 50,
) -> list[Incident]:
    """查询事件列表。"""
    stmt = select(Incident)

    if filters.status:
        stmt = stmt.where(Incident.status == filters.status)
    if filters.severity:
        stmt = stmt.where(Incident.severity == filters.severity)
    if filters.assigned_to is not None:
        stmt = stmt.where(Incident.assigned_to == filters.assigned_to)
    if filters.start_time:
        stmt = stmt.where(Incident.created_at >= filters.start_time)
    if filters.end_time:
        stmt = stmt.where(Incident.created_at <= filters.end_time)

    # 前缀与 ASN 过滤需要 JSON 包含查询（简化为内存过滤）
    stmt = stmt.order_by(Incident.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    incidents = list(result.scalars().all())

    # 内存过滤前缀与 ASN
    if filters.prefix:
        incidents = [
            inc for inc in incidents
            if inc.affected_prefixes and filters.prefix in inc.affected_prefixes
        ]
    if filters.asn is not None:
        incidents = [
            inc for inc in incidents
            if inc.affected_asns and filters.asn in inc.affected_asns
        ]

    return incidents


async def count_incidents(
    db: AsyncSession, filters: IncidentQueryParams
) -> int:
    """统计事件数量。"""
    stmt = select(func.count(Incident.id))

    if filters.status:
        stmt = stmt.where(Incident.status == filters.status)
    if filters.severity:
        stmt = stmt.where(Incident.severity == filters.severity)
    if filters.assigned_to is not None:
        stmt = stmt.where(Incident.assigned_to == filters.assigned_to)
    if filters.start_time:
        stmt = stmt.where(Incident.created_at >= filters.start_time)
    if filters.end_time:
        stmt = stmt.where(Incident.created_at <= filters.end_time)

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_incident(
    db: AsyncSession,
    incident: Incident,
    incident_update: IncidentUpdate,
) -> Incident:
    """更新事件。

    Args:
        db: 异步数据库会话
        incident: 事件对象
        incident_update: 更新请求

    Returns:
        更新后的事件对象
    """
    update_data = incident_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)

    # 添加时间线条目
    now = datetime.now(timezone.utc)
    timeline = incident.timeline or []
    changed_fields = list(update_data.keys())
    timeline.append({
        "timestamp": now.isoformat(),
        "event_type": "updated",
        "description": f"更新字段：{', '.join(changed_fields)}",
        "operator": None,
    })
    incident.timeline = timeline
    incident.last_seen_at = now

    await db.flush()
    logger.info(
        "事件已更新",
        incident_id=incident.id,
        fields=changed_fields,
    )
    return incident


async def assign_incident(
    db: AsyncSession, incident_id: int, user_id: int
) -> Incident | None:
    """分派事件给指定用户。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID
        user_id: 用户 ID

    Returns:
        更新后的事件对象，事件不存在返回 None
    """
    incident = await get_incident(db, incident_id)
    if incident is None:
        return None

    incident.assigned_to = user_id
    if incident.status == "open":
        incident.status = "investigating"

    # 添加时间线条目
    now = datetime.now(timezone.utc)
    timeline = incident.timeline or []
    timeline.append({
        "timestamp": now.isoformat(),
        "event_type": "assigned",
        "description": f"事件分派给用户 {user_id}",
        "operator": None,
    })
    incident.timeline = timeline
    incident.last_seen_at = now

    await db.flush()
    logger.info(
        "事件已分派",
        incident_id=incident_id,
        user_id=user_id,
    )
    return incident


async def escalate_incident(
    db: AsyncSession, incident_id: int
) -> Incident | None:
    """升级事件严重等级。

    将事件严重等级提升一级（如 P3 → P2）。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID

    Returns:
        更新后的事件对象，事件不存在返回 None
    """
    incident = await get_incident(db, incident_id)
    if incident is None:
        return None

    current_level = SEVERITY_ORDER.get(incident.severity, 3)
    if current_level > 0:  # 不是 P0
        # 找到比当前严重一级的等级
        for sev, order in SEVERITY_ORDER.items():
            if order == current_level - 1:
                incident.severity = sev
                break

    # 添加时间线条目
    now = datetime.now(timezone.utc)
    timeline = incident.timeline or []
    timeline.append({
        "timestamp": now.isoformat(),
        "event_type": "escalated",
        "description": f"事件升级为 {incident.severity}",
        "operator": None,
    })
    incident.timeline = timeline
    incident.last_seen_at = now

    await db.flush()
    logger.info(
        "事件已升级",
        incident_id=incident_id,
        severity=incident.severity,
    )
    return incident


async def close_incident(
    db: AsyncSession, incident_id: int, resolution: str
) -> Incident | None:
    """关闭事件。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID
        resolution: 处置结论

    Returns:
        更新后的事件对象，事件不存在返回 None
    """
    incident = await get_incident(db, incident_id)
    if incident is None:
        return None

    now = datetime.now(timezone.utc)
    incident.status = "closed"
    incident.resolution = resolution
    incident.closed_at = now

    # 添加时间线条目
    timeline = incident.timeline or []
    timeline.append({
        "timestamp": now.isoformat(),
        "event_type": "closed",
        "description": f"事件已关闭：{resolution}",
        "operator": None,
    })
    incident.timeline = timeline
    incident.last_seen_at = now

    await db.flush()
    logger.info(
        "事件已关闭",
        incident_id=incident_id,
    )
    return incident


async def add_timeline_event(
    db: AsyncSession,
    incident_id: int,
    event: TimelineEvent,
) -> Incident | None:
    """添加时间线事件。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID
        event: 时间线条目

    Returns:
        更新后的事件对象，事件不存在返回 None
    """
    incident = await get_incident(db, incident_id)
    if incident is None:
        return None

    timeline = incident.timeline or []
    timeline.append({
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type,
        "description": event.description,
        "operator": event.operator,
    })
    incident.timeline = timeline
    incident.last_seen_at = datetime.now(timezone.utc)

    await db.flush()
    logger.info(
        "时间线事件已添加",
        incident_id=incident_id,
        event_type=event.event_type,
    )
    return incident


async def _link_alerts_to_incident(
    db: AsyncSession, alert_ids: list[int], incident_id: int
) -> None:
    """将告警关联到事件。"""
    if not alert_ids:
        return
    stmt = select(Alert).where(Alert.id.in_(alert_ids))
    result = await db.execute(stmt)
    alerts = list(result.scalars().all())
    for alert in alerts:
        alert.incident_id = incident_id
        if alert.status == "new":
            alert.status = "assigned"
    await db.flush()


__all__ = [
    "add_timeline_event",
    "assign_incident",
    "close_incident",
    "count_incidents",
    "create_incident",
    "escalate_incident",
    "get_incident",
    "get_incidents",
    "update_incident",
]
