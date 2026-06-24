"""MOAS（Multiple Origin AS）异常检测器。

识别前缀被多个 origin AS 宣告的异常情况，结合 ASN 类型与历史模式区分
授权多 origin、Anycast、客户托管、清洗业务与未知双 origin 等场景。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement
from app.schemas.detection import MOASDetectionResult

logger = get_logger("app.detection.moas")


async def detect_moas(
    db: AsyncSession, announcement: BGPAnnouncement
) -> MOASDetectionResult:
    """MOAS 异常检测。

    检测流程：
    1. 识别前缀被多个 origin AS 宣告
    2. 区分：授权多 origin、Anycast、客户托管、清洗业务、未知双 origin
    3. 关联 ASN 类型（asn_type 字段）和历史模式

    Args:
        db: 异步数据库会话
        announcement: BGP 公告对象

    Returns:
        MOAS 检测结果
    """
    prefix = announcement.prefix
    origin_as = announcement.origin_as

    if origin_as is None:
        return MOASDetectionResult(
            alert_type="moas",
            severity="P3",
            description="公告缺少 origin_as，无法判定 MOAS",
            is_detected=False,
        )

    # 查询近期该前缀的所有 origin AS
    recent_origin_asns = await _get_recent_origin_asns(db, prefix)

    # 仅一个 origin AS，不构成 MOAS
    if len(recent_origin_asns) <= 1:
        return MOASDetectionResult(
            alert_type="moas",
            severity="P3",
            description=f"前缀 {prefix} 仅由单一 AS 宣告，无 MOAS",
            origin_as_list=recent_origin_asns,
            is_detected=False,
            confidence=0.7,
        )

    # 查询每个 origin AS 的元信息
    asn_meta = await _get_asn_metadata(db, recent_origin_asns)

    # 查询历史 MOAS 模式
    historical_moas = await _get_historical_moas(db, prefix)

    # 分类 MOAS 类型
    moas_type, severity, description = _classify_moas(
        recent_origin_asns, asn_meta, historical_moas
    )

    is_anomaly = moas_type == "unknown"
    if is_anomaly:
        severity = "P2"
        description = (
            f"前缀 {prefix} 被多个未知关系 AS 宣告："
            f"{recent_origin_asns}"
        )

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "current_origin_as": origin_as,
        "all_origin_asns": recent_origin_asns,
        "asn_metadata": asn_meta,
        "historical_moas": historical_moas,
        "moas_type": moas_type,
    }

    return MOASDetectionResult(
        alert_type="moas",
        severity=severity,
        description=description,
        evidence=evidence,
        origin_as_list=recent_origin_asns,
        moas_type=moas_type,
        is_detected=is_anomaly,
        risk_score=0.0,
        confidence=0.8 if is_anomaly else 0.6,
    )


async def _get_recent_origin_asns(
    db: AsyncSession,
    prefix: str,
    lookback_minutes: int = 60,
) -> list[int]:
    """查询近期该前缀的所有 origin AS。"""
    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    stmt = (
        select(BGPAnnouncement.origin_as)
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as.is_not(None))
        .where(BGPAnnouncement.timestamp >= since)
        .distinct()
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all() if row[0] is not None]


async def _get_asn_metadata(
    db: AsyncSession, asn_list: list[int]
) -> dict[int, dict[str, Any]]:
    """查询 ASN 元信息（类型、关系标签等）。"""
    if not asn_list:
        return {}
    stmt = select(ASN).where(ASN.asn.in_(asn_list))
    result = await db.execute(stmt)
    asn_objects = list(result.scalars().all())
    return {
        asn.asn: {
            "asn": asn.asn,
            "name": asn.name,
            "asn_type": asn.asn_type,
            "relationship_tags": asn.relationship_tags or [],
            "risk_profile": asn.risk_profile,
        }
        for asn in asn_objects
    }


async def _get_historical_moas(
    db: AsyncSession,
    prefix: str,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """查询历史 MOAS 模式。"""
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    stmt = (
        select(
            BGPAnnouncement.origin_as,
            func.count(BGPAnnouncement.id).label("cnt"),
        )
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as.is_not(None))
        .where(BGPAnnouncement.timestamp >= since)
        .group_by(BGPAnnouncement.origin_as)
        .order_by(func.count(BGPAnnouncement.id).desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return {
        "historical_origin_asns": [row[0] for row in rows],
        "historical_counts": {row[0]: row[1] for row in rows},
        "lookback_days": lookback_days,
    }


def _classify_moas(
    origin_asns: list[int],
    asn_meta: dict[int, dict[str, Any]],
    historical_moas: dict[str, Any],
) -> tuple[str, str, str]:
    """根据 ASN 元信息与历史模式分类 MOAS 类型。

    Returns:
        (moas_type, severity, description) 三元组
    """
    historical_asns = set(historical_moas.get("historical_origin_asns", []))
    current_asns = set(origin_asns)

    # 全部 AS 都在历史基线中 → 授权多 origin
    if current_asns.issubset(historical_asns) and len(historical_asns) >= 2:
        return (
            "authorized_multi_origin",
            "P3",
            "前缀被多个 AS 宣告，但全部 AS 均在历史基线中，判定为授权多 origin",
        )

    # 检查 ASN 类型，识别 Anycast / 清洗业务 / 客户托管
    asn_types = []
    for asn in origin_asns:
        meta = asn_meta.get(asn)
        if meta:
            asn_types.append(meta.get("asn_type", "unknown"))
        else:
            asn_types.append("unknown")

    # 任一 AS 是清洗中心
    if "scrubber" in asn_types:
        return (
            "scrubber",
            "P3",
            "前缀被多个 AS 宣告，其中包含清洗中心 AS，判定为清洗业务",
        )

    # 多个 AS 都是自有或客户 → 客户托管或授权
    own_or_customer = {"own", "customer"}
    if all(t in own_or_customer for t in asn_types):
        return (
            "managed",
            "P3",
            "前缀被多个自有/客户 AS 宣告，判定为客户托管",
        )

    # 检查关系标签是否标识为 anycast
    anycast_flag = False
    for asn in origin_asns:
        meta = asn_meta.get(asn)
        if meta:
            tags = meta.get("relationship_tags", [])
            if "anycast" in tags:
                anycast_flag = True
                break
    if anycast_flag:
        return (
            "anycast",
            "P3",
            "前缀被多个 AS 宣告，关系标签标识为 Anycast",
        )

    # 未知双 origin
    return (
        "unknown",
        "P2",
        f"前缀被多个未知关系 AS 宣告：{origin_asns}",
    )


__all__ = ["detect_moas"]
