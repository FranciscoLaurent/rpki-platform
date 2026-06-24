"""良性冲突记录管理服务。

提供良性冲突记录的创建、查询、状态更新、统计摘要与告警关联能力。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.benign_conflict import BenignConflictRecord
from app.models.detection import Alert
from app.schemas.benign_conflict import (
    BenignConflictRecordCreate,
    BenignConflictQueryParams,
    BenignConflictSummary,
    BenignConflictTypeSummary,
)

logger = get_logger("app.benign_conflict_service")


async def create_benign_conflict_record(
    db: AsyncSession, record_data: BenignConflictRecordCreate
) -> BenignConflictRecord:
    """创建良性冲突记录。

    Args:
        db: 异步数据库会话
        record_data: 良性冲突记录创建数据

    Returns:
        创建后的良性冲突记录对象
    """
    record = BenignConflictRecord(
        alert_id=record_data.alert_id,
        conflict_type=record_data.conflict_type,
        prefix=record_data.prefix,
        origin_as=record_data.origin_as,
        expected_origin_as=record_data.expected_origin_as,
        confidence=record_data.confidence,
        evidence=record_data.evidence,
        recommendation=record_data.recommendation,
        status=record_data.status,
        valid_until=record_data.valid_until,
        related_work_order=record_data.related_work_order,
        tenant_id=record_data.tenant_id,
    )
    db.add(record)
    await db.flush()
    await db.commit()
    await db.refresh(record)

    logger.info(
        "良性冲突记录已创建",
        record_id=record.id,
        conflict_type=record.conflict_type,
        prefix=record.prefix,
    )
    return record


async def get_benign_conflict_record(
    db: AsyncSession, record_id: int
) -> BenignConflictRecord | None:
    """根据 ID 获取良性冲突记录。"""
    stmt = select(BenignConflictRecord).where(
        BenignConflictRecord.id == record_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_benign_conflict_records(
    db: AsyncSession,
    query_params: BenignConflictQueryParams,
    skip: int = 0,
    limit: int = 50,
) -> list[BenignConflictRecord]:
    """查询良性冲突记录列表。

    Args:
        db: 异步数据库会话
        query_params: 查询参数
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        良性冲突记录列表
    """
    stmt = select(BenignConflictRecord)

    if query_params.prefix:
        stmt = stmt.where(BenignConflictRecord.prefix == query_params.prefix)
    if query_params.origin_as is not None:
        stmt = stmt.where(BenignConflictRecord.origin_as == query_params.origin_as)
    if query_params.conflict_type:
        stmt = stmt.where(
            BenignConflictRecord.conflict_type == query_params.conflict_type
        )
    if query_params.status:
        stmt = stmt.where(BenignConflictRecord.status == query_params.status)
    if query_params.start_time:
        stmt = stmt.where(
            BenignConflictRecord.created_at >= query_params.start_time
        )
    if query_params.end_time:
        stmt = stmt.where(
            BenignConflictRecord.created_at <= query_params.end_time
        )

    stmt = stmt.order_by(
        BenignConflictRecord.created_at.desc()
    ).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_benign_conflict_records(
    db: AsyncSession, query_params: BenignConflictQueryParams
) -> int:
    """统计良性冲突记录数量。"""
    stmt = select(func.count(BenignConflictRecord.id))

    if query_params.prefix:
        stmt = stmt.where(BenignConflictRecord.prefix == query_params.prefix)
    if query_params.origin_as is not None:
        stmt = stmt.where(BenignConflictRecord.origin_as == query_params.origin_as)
    if query_params.conflict_type:
        stmt = stmt.where(
            BenignConflictRecord.conflict_type == query_params.conflict_type
        )
    if query_params.status:
        stmt = stmt.where(BenignConflictRecord.status == query_params.status)
    if query_params.start_time:
        stmt = stmt.where(
            BenignConflictRecord.created_at >= query_params.start_time
        )
    if query_params.end_time:
        stmt = stmt.where(
            BenignConflictRecord.created_at <= query_params.end_time
        )

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_benign_conflict_status(
    db: AsyncSession,
    record: BenignConflictRecord,
    status: str,
    recommendation: str | None = None,
    related_work_order: str | None = None,
) -> BenignConflictRecord:
    """更新良性冲突记录状态。

    Args:
        db: 异步数据库会话
        record: 待更新的良性冲突记录对象
        status: 新状态
        recommendation: 处理建议（可选）
        related_work_order: 关联工单号（可选）

    Returns:
        更新后的良性冲突记录对象
    """
    record.status = status
    if recommendation is not None:
        record.recommendation = recommendation
    if related_work_order is not None:
        record.related_work_order = related_work_order

    await db.flush()
    await db.commit()
    await db.refresh(record)

    logger.info(
        "良性冲突记录状态已更新",
        record_id=record.id,
        status=status,
    )
    return record


async def get_benign_conflict_summary(
    db: AsyncSession,
) -> BenignConflictSummary:
    """获取良性冲突统计摘要。

    Args:
        db: 异步数据库会话

    Returns:
        良性冲突统计摘要
    """
    # 总数
    total_stmt = select(func.count(BenignConflictRecord.id))
    total_result = await db.execute(total_stmt)
    total = int(total_result.scalar_one() or 0)

    # 按状态统计
    status_stmt = (
        select(BenignConflictRecord.status, func.count(BenignConflictRecord.id))
        .group_by(BenignConflictRecord.status)
    )
    status_result = await db.execute(status_stmt)
    status_counts = {row[0]: int(row[1]) for row in status_result.all()}

    # 按类型统计
    type_stmt = (
        select(
            BenignConflictRecord.conflict_type,
            BenignConflictRecord.status,
            func.count(BenignConflictRecord.id),
            func.avg(BenignConflictRecord.confidence),
        )
        .group_by(
            BenignConflictRecord.conflict_type,
            BenignConflictRecord.status,
        )
    )
    type_result = await db.execute(type_stmt)

    # 聚合按类型统计
    type_summary: dict[str, dict[str, Any]] = {}
    for row in type_result.all():
        conflict_type = row[0]
        status = row[1]
        count = int(row[2])
        avg_conf = float(row[3] or 0.0)

        if conflict_type not in type_summary:
            type_summary[conflict_type] = {
                "conflict_type": conflict_type,
                "count": 0,
                "confirmed_count": 0,
                "suspected_count": 0,
                "dismissed_count": 0,
                "avg_confidence": 0.0,
                "_confidence_sum": 0.0,
            }

        type_summary[conflict_type]["count"] += count
        type_summary[conflict_type]["_confidence_sum"] += avg_conf * count
        if status == "confirmed":
            type_summary[conflict_type]["confirmed_count"] += count
        elif status == "suspected":
            type_summary[conflict_type]["suspected_count"] += count
        elif status == "dismissed":
            type_summary[conflict_type]["dismissed_count"] += count

    # 计算平均置信度
    by_type: list[BenignConflictTypeSummary] = []
    for summary in type_summary.values():
        count = summary["count"]
        avg_conf = summary["_confidence_sum"] / count if count > 0 else 0.0
        by_type.append(
            BenignConflictTypeSummary(
                conflict_type=summary["conflict_type"],
                count=count,
                confirmed_count=summary["confirmed_count"],
                suspected_count=summary["suspected_count"],
                dismissed_count=summary["dismissed_count"],
                avg_confidence=round(avg_conf, 4),
            )
        )

    # 最近 24 小时新增数
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_stmt = select(func.count(BenignConflictRecord.id)).where(
        BenignConflictRecord.created_at >= since
    )
    recent_result = await db.execute(recent_stmt)
    recent_24h = int(recent_result.scalar_one() or 0)

    return BenignConflictSummary(
        total=total,
        confirmed=status_counts.get("confirmed", 0),
        suspected=status_counts.get("suspected", 0),
        dismissed=status_counts.get("dismissed", 0),
        by_type=by_type,
        recent_24h=recent_24h,
    )


async def link_alert_to_benign_conflict(
    db: AsyncSession, alert_id: int, conflict_id: int
) -> BenignConflictRecord | None:
    """关联告警到良性冲突记录。

    将良性冲突记录的 ``alert_id`` 设置为指定告警 ID，
    同时更新告警的 ``is_benign_conflict`` 与 ``benign_conflict_type`` 字段。

    Args:
        db: 异步数据库会话
        alert_id: 告警 ID
        conflict_id: 良性冲突记录 ID

    Returns:
        更新后的良性冲突记录对象，记录不存在返回 None
    """
    # 查询良性冲突记录
    record = await get_benign_conflict_record(db, conflict_id)
    if record is None:
        return None

    # 关联告警
    record.alert_id = alert_id

    # 同步更新告警的良性冲突标记
    alert_stmt = select(Alert).where(Alert.id == alert_id)
    alert_result = await db.execute(alert_stmt)
    alert = alert_result.scalar_one_or_none()
    if alert is not None:
        alert.is_benign_conflict = True
        alert.benign_conflict_type = record.conflict_type

    await db.flush()
    await db.commit()
    await db.refresh(record)

    logger.info(
        "告警已关联到良性冲突记录",
        alert_id=alert_id,
        conflict_id=conflict_id,
    )
    return record


__all__ = [
    "count_benign_conflict_records",
    "create_benign_conflict_record",
    "get_benign_conflict_record",
    "get_benign_conflict_records",
    "get_benign_conflict_summary",
    "link_alert_to_benign_conflict",
    "update_benign_conflict_status",
]
