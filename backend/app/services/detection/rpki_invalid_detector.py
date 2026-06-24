"""RPKI Invalid 传播统计检测器。

统计 Invalid 路由被哪些观察点接收、传播或拒绝，反映真实影响面。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.schemas.detection import RPKIInvalidResult

logger = get_logger("app.detection.rpki_invalid")


async def detect_rpki_invalid_propagation(
    db: AsyncSession,
    prefix: str,
    lookback_hours: int = 24,
) -> RPKIInvalidResult:
    """RPKI Invalid 传播统计。

    检测流程：
    1. 查询指定前缀的所有 Invalid 公告
    2. 统计 Invalid 路由被哪些观察点接收、传播
    3. 反映真实影响面

    Args:
        db: 异步数据库会话
        prefix: 待检测的前缀
        lookback_hours: 回溯小时数

    Returns:
        RPKI Invalid 传播检测结果
    """
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)

    # 查询该前缀的所有 Invalid 公告
    stmt = (
        select(
            BGPAnnouncement.origin_as,
            BGPAnnouncement.observation_point_id,
            BGPAnnouncement.rpki_invalid_reason,
            BGPAnnouncement.as_path,
        )
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.rpki_validation_status == "invalid")
        .where(BGPAnnouncement.timestamp >= since)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return RPKIInvalidResult(
            alert_type="rpki_invalid",
            severity="P3",
            description=f"前缀 {prefix} 在 {lookback_hours} 小时内无 Invalid 公告",
            is_detected=False,
            confidence=0.7,
        )

    # 统计传播观察点
    propagation_points: list[int] = []
    invalid_reasons: dict[str, int] = {}
    origin_asns: set[int] = set()
    for row in rows:
        if row.observation_point_id is not None:
            propagation_points.append(row.observation_point_id)
        if row.rpki_invalid_reason:
            invalid_reasons[row.rpki_invalid_reason] = (
                invalid_reasons.get(row.rpki_invalid_reason, 0) + 1
            )
        if row.origin_as is not None:
            origin_asns.add(row.origin_as)

    # 去重观察点
    unique_points = list(set(propagation_points))
    propagation_count = len(unique_points)

    # 主要 Invalid 原因
    primary_reason = max(invalid_reasons, key=invalid_reasons.get) if invalid_reasons else None

    # 判定严重等级
    is_anomaly = propagation_count > 0
    severity = "P3"
    description = "未检测到 RPKI Invalid 传播"

    if is_anomaly:
        if propagation_count >= 10:
            severity = "P0"
        elif propagation_count >= 5:
            severity = "P1"
        else:
            severity = "P2"
        description = (
            f"前缀 {prefix} 的 RPKI Invalid 路由被 {propagation_count} "
            f"个观察点接收传播（原因：{primary_reason}）"
        )

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "lookback_hours": lookback_hours,
        "invalid_announcement_count": len(rows),
        "propagation_count": propagation_count,
        "propagation_points": unique_points,
        "invalid_reasons": invalid_reasons,
        "primary_reason": primary_reason,
        "origin_asns": sorted(origin_asns),
    }

    return RPKIInvalidResult(
        alert_type="rpki_invalid",
        severity=severity,
        description=description,
        evidence=evidence,
        invalid_reason=primary_reason,
        propagation_count=propagation_count,
        propagation_points=unique_points,
        is_detected=is_anomaly,
        risk_score=0.0,
        confidence=0.9 if is_anomaly else 0.5,
    )


__all__ = ["detect_rpki_invalid_propagation"]
