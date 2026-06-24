"""撤路与震荡检测器。

检测大范围撤路、频繁 announce/withdraw 震荡、前缀数突变与收敛异常。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement, BGPWithdraw
from app.schemas.detection import WithdrawFlapResult

logger = get_logger("app.detection.withdraw")


async def detect_withdraw_flap(
    db: AsyncSession,
    prefix: str,
    time_window: int = 60,
) -> WithdrawFlapResult:
    """撤路与震荡检测。

    检测流程：
    1. 大范围撤路检测（多个观察点同时撤路）
    2. 频繁 announce/withdraw 震荡检测
    3. 前缀数突变检测
    4. 收敛异常检测

    Args:
        db: 异步数据库会话
        prefix: 待检测的前缀
        time_window: 检测时间窗口（分钟）

    Returns:
        撤路与震荡检测结果
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=time_window)

    # 1. 统计撤路次数与受影响观察点
    withdraw_count, withdraw_points = await _count_withdraws(
        db, prefix, since
    )

    # 2. 统计公告次数
    announce_count, announce_points = await _count_announcements(
        db, prefix, since
    )

    # 3. 计算震荡频率
    total_events = withdraw_count + announce_count
    flap_rate = total_events / time_window if time_window > 0 else 0.0

    # 4. 检测大范围撤路
    large_scale_withdraw = withdraw_points >= 5

    # 5. 检测频繁震荡
    frequent_flap = flap_rate >= 0.5  # 平均每分钟 0.5 次以上

    # 综合判定
    is_anomaly = False
    severity = "P3"
    description = "未检测到撤路与震荡异常"

    if large_scale_withdraw:
        is_anomaly = True
        severity = "P1"
        description = (
            f"大范围撤路：前缀 {prefix} 在 {time_window} 分钟内"
            f"被 {withdraw_points} 个观察点撤路"
        )

    if frequent_flap:
        is_anomaly = True
        if severity == "P3":
            severity = "P1"
        description = (
            f"频繁震荡：前缀 {prefix} 在 {time_window} 分钟内"
            f"发生 {total_events} 次事件（频率 {flap_rate:.2f} 次/分钟）"
        )

    # 6. 收敛异常检测：公告数远超撤路数
    if announce_count >= 10 and announce_count > withdraw_count * 3:
        is_anomaly = True
        if severity == "P3":
            severity = "P2"
        description = (
            f"收敛异常：前缀 {prefix} 公告数 {announce_count} "
            f"远超撤路数 {withdraw_count}"
        )

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "time_window_minutes": time_window,
        "withdraw_count": withdraw_count,
        "announce_count": announce_count,
        "affected_observation_points": max(withdraw_points, announce_points),
        "flap_rate": flap_rate,
        "large_scale_withdraw": large_scale_withdraw,
        "frequent_flap": frequent_flap,
    }

    return WithdrawFlapResult(
        alert_type="withdraw_flap",
        severity=severity,
        description=description,
        evidence=evidence,
        withdraw_count=withdraw_count,
        announce_count=announce_count,
        affected_observation_points=max(withdraw_points, announce_points),
        flap_rate=flap_rate,
        is_detected=is_anomaly,
        risk_score=0.0,
        confidence=0.8 if is_anomaly else 0.5,
    )


async def _count_withdraws(
    db: AsyncSession, prefix: str, since: datetime
) -> tuple[int, int]:
    """统计指定前缀的撤路次数与受影响观察点数。

    Returns:
        (撤路次数, 受影响观察点数)
    """
    stmt = (
        select(
            func.count(BGPWithdraw.id).label("cnt"),
            func.count(func.distinct(BGPWithdraw.observation_point_id)).label(
                "points"
            ),
        )
        .where(BGPWithdraw.prefix == prefix)
        .where(BGPWithdraw.timestamp >= since)
    )
    result = await db.execute(stmt)
    row = result.one()
    return int(row.cnt or 0), int(row.points or 0)


async def _count_announcements(
    db: AsyncSession, prefix: str, since: datetime
) -> tuple[int, int]:
    """统计指定前缀的公告次数与观察点数。

    Returns:
        (公告次数, 观察点数)
    """
    stmt = (
        select(
            func.count(BGPAnnouncement.id).label("cnt"),
            func.count(
                func.distinct(BGPAnnouncement.observation_point_id)
            ).label("points"),
        )
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.timestamp >= since)
    )
    result = await db.execute(stmt)
    row = result.one()
    return int(row.cnt or 0), int(row.points or 0)


__all__ = ["detect_withdraw_flap"]
