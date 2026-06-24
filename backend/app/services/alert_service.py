"""告警服务。

提供告警的创建、查询、状态更新、去重、聚合与事件归并能力。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import Alert, Incident
from app.schemas.detection import (
    AlertQueryParams,
)

logger = get_logger("app.alert_service")


async def create_alert(db: AsyncSession, alert_data: dict[str, Any]) -> Alert:
    """创建告警。

    Args:
        db: 异步数据库会话
        alert_data: 告警数据字典

    Returns:
        创建的告警对象（已持久化）
    """
    now = datetime.now(UTC)
    alert = Alert(
        rule_id=alert_data.get("rule_id"),
        alert_type=alert_data["alert_type"],
        severity=alert_data.get("severity", "P3"),
        prefix=alert_data["prefix"],
        origin_as=alert_data.get("origin_as"),
        as_path=alert_data.get("as_path"),
        observation_point_id=alert_data.get("observation_point_id"),
        title=alert_data["title"],
        description=alert_data.get("description"),
        evidence=alert_data.get("evidence"),
        risk_score=alert_data.get("risk_score", 0.0),
        confidence=alert_data.get("confidence", 0.0),
        status="new",
        is_benign_conflict=alert_data.get("is_benign_conflict", False),
        benign_conflict_type=alert_data.get("benign_conflict_type"),
        first_seen_at=alert_data.get("first_seen_at", now),
        last_seen_at=alert_data.get("last_seen_at", now),
        tenant_id=alert_data.get("tenant_id"),
    )
    db.add(alert)
    await db.flush()
    logger.info(
        "告警已创建",
        alert_id=alert.id,
        alert_type=alert.alert_type,
        prefix=alert.prefix,
    )
    return alert


async def get_alert(db: AsyncSession, alert_id: int) -> Alert | None:
    """根据 ID 获取告警。"""
    stmt = select(Alert).where(Alert.id == alert_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_alerts(
    db: AsyncSession,
    query_params: AlertQueryParams,
    skip: int = 0,
    limit: int = 50,
) -> list[Alert]:
    """查询告警列表。

    Args:
        db: 异步数据库会话
        query_params: 查询参数
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        告警列表
    """
    stmt = select(Alert)

    if query_params.prefix:
        stmt = stmt.where(Alert.prefix == query_params.prefix)
    if query_params.origin_as is not None:
        stmt = stmt.where(Alert.origin_as == query_params.origin_as)
    if query_params.severity:
        stmt = stmt.where(Alert.severity == query_params.severity)
    if query_params.status:
        stmt = stmt.where(Alert.status == query_params.status)
    if query_params.alert_type:
        stmt = stmt.where(Alert.alert_type == query_params.alert_type)
    if query_params.incident_id is not None:
        stmt = stmt.where(Alert.incident_id == query_params.incident_id)
    if query_params.start_time:
        stmt = stmt.where(Alert.created_at >= query_params.start_time)
    if query_params.end_time:
        stmt = stmt.where(Alert.created_at <= query_params.end_time)

    stmt = stmt.order_by(Alert.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_alerts(db: AsyncSession, query_params: AlertQueryParams) -> int:
    """统计告警数量。"""
    stmt = select(func.count(Alert.id))

    if query_params.prefix:
        stmt = stmt.where(Alert.prefix == query_params.prefix)
    if query_params.origin_as is not None:
        stmt = stmt.where(Alert.origin_as == query_params.origin_as)
    if query_params.severity:
        stmt = stmt.where(Alert.severity == query_params.severity)
    if query_params.status:
        stmt = stmt.where(Alert.status == query_params.status)
    if query_params.alert_type:
        stmt = stmt.where(Alert.alert_type == query_params.alert_type)
    if query_params.incident_id is not None:
        stmt = stmt.where(Alert.incident_id == query_params.incident_id)
    if query_params.start_time:
        stmt = stmt.where(Alert.created_at >= query_params.start_time)
    if query_params.end_time:
        stmt = stmt.where(Alert.created_at <= query_params.end_time)

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_alert_status(
    db: AsyncSession,
    alert: Alert,
    status: str,
    is_benign_conflict: bool | None = None,
    benign_conflict_type: str | None = None,
) -> Alert:
    """更新告警状态。

    Args:
        db: 异步数据库会话
        alert: 告警对象
        status: 新状态
        is_benign_conflict: 是否标记为良性冲突
        benign_conflict_type: 良性冲突类型

    Returns:
        更新后的告警对象
    """
    alert.status = status
    if is_benign_conflict is not None:
        alert.is_benign_conflict = is_benign_conflict
    if benign_conflict_type is not None:
        alert.benign_conflict_type = benign_conflict_type

    await db.flush()
    logger.info(
        "告警状态已更新",
        alert_id=alert.id,
        status=status,
    )
    return alert


async def deduplicate_alerts(db: AsyncSession, alerts: list[Alert]) -> list[Alert]:
    """告警去重。

    对同一前缀、同一 origin AS、同一告警类型的告警进行去重，
    保留风险评分最高的一条。

    Args:
        db: 异步数据库会话
        alerts: 待去重的告警列表

    Returns:
        去重后的告警列表
    """
    seen: dict[tuple[str, int | None, str], Alert] = {}
    for alert in alerts:
        key = (alert.prefix, alert.origin_as, alert.alert_type)
        if key not in seen:
            seen[key] = alert
        else:
            # 保留风险评分更高的
            if alert.risk_score > seen[key].risk_score:
                seen[key] = alert
    return list(seen.values())


async def aggregate_alerts(db: AsyncSession, alerts: list[Alert]) -> list[dict[str, Any]]:
    """告警聚合与同源事件归并。

    将同源告警（相同前缀、相同 origin AS、相同告警类型）归并到同一事件。

    Args:
        db: 异步数据库会话
        alerts: 待聚合的告警列表

    Returns:
        聚合后的事件摘要列表
    """
    groups: dict[tuple[str, int | None, str], list[Alert]] = {}
    for alert in alerts:
        key = (alert.prefix, alert.origin_as, alert.alert_type)
        groups.setdefault(key, []).append(alert)

    aggregated: list[dict[str, Any]] = []
    for (prefix, origin_as, alert_type), group_alerts in groups.items():
        max_severity = _max_severity([a.severity for a in group_alerts])
        max_risk = max(a.risk_score for a in group_alerts)
        aggregated.append(
            {
                "prefix": prefix,
                "origin_as": origin_as,
                "alert_type": alert_type,
                "alert_count": len(group_alerts),
                "alert_ids": [a.id for a in group_alerts],
                "max_severity": max_severity,
                "max_risk_score": max_risk,
                "first_seen_at": (
                    min(a.first_seen_at or a.created_at for a in group_alerts).isoformat()
                    if group_alerts
                    else None
                ),
                "last_seen_at": (
                    max(a.last_seen_at or a.created_at for a in group_alerts).isoformat()
                    if group_alerts
                    else None
                ),
            }
        )

    return aggregated


async def assign_alert_to_incident(
    db: AsyncSession, alert_id: int, incident_id: int
) -> Alert | None:
    """关联告警到事件。

    Args:
        db: 异步数据库会话
        alert_id: 告警 ID
        incident_id: 事件 ID

    Returns:
        更新后的告警对象，告警不存在返回 None
    """
    alert = await get_alert(db, alert_id)
    if alert is None:
        return None

    alert.incident_id = incident_id
    alert.status = "assigned"

    # 同步更新事件的 alert_ids
    incident_stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(incident_stmt)
    incident = result.scalar_one_or_none()
    if incident is not None:
        existing_ids = incident.alert_ids or []
        if alert_id not in existing_ids:
            existing_ids.append(alert_id)
            incident.alert_ids = existing_ids

    await db.flush()
    logger.info(
        "告警已关联到事件",
        alert_id=alert_id,
        incident_id=incident_id,
    )
    return alert


def _max_severity(severities: list[str]) -> str:
    """获取最高严重等级。"""
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    if not severities:
        return "P3"
    return min(severities, key=lambda s: order.get(s, 3))


__all__ = [
    "aggregate_alerts",
    "assign_alert_to_incident",
    "count_alerts",
    "create_alert",
    "deduplicate_alerts",
    "get_alert",
    "get_alerts",
    "update_alert_status",
]
