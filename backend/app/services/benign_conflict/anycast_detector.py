"""Anycast 扩容识别检测器。

识别 Anycast 节点扩容导致的多 origin AS 良性冲突。

检测流程：
1. 检查 origin_as 是否为已登记的 Anycast 节点 ASN
2. 检查地域和业务标签
3. 检查历史多 origin 模式

注意：良性冲突识别只降低误报优先级，不能替代安全验证。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.benign_conflict import AnycastNode
from app.models.bgp import BGPAnnouncement
from app.models.detection import Alert
from app.schemas.benign_conflict import BenignConflictAnalysisResult

logger = get_logger("app.benign_conflict.anycast")


async def detect_anycast_expansion(
    db: AsyncSession, alert: Alert
) -> BenignConflictAnalysisResult:
    """识别 Anycast 扩容。

    Args:
        db: 异步数据库会话
        alert: 待分析的告警对象

    Returns:
        良性冲突分析结果。若识别为 Anycast 扩容，``is_benign`` 为 True，
        ``conflict_type`` 为 ``anycast_expansion``。
    """
    prefix = alert.prefix
    origin_as = alert.origin_as

    if origin_as is None:
        return BenignConflictAnalysisResult(
            is_benign=False,
            recommendation="告警缺少 origin_as，无法判定 Anycast 扩容",
        )

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "checks": {},
    }
    confidence = 0.0

    # 1. 检查 origin_as 是否为已登记的 Anycast 节点 ASN
    anycast_node = await _check_anycast_node(db, origin_as, prefix)
    evidence["checks"]["is_anycast_node"] = anycast_node is not None
    if anycast_node is not None:
        evidence["anycast_node"] = {
            "id": anycast_node.id,
            "node_asn": anycast_node.node_asn,
            "prefix": anycast_node.prefix,
            "region": anycast_node.region,
            "site": anycast_node.site,
            "business_tag": anycast_node.business_tag,
            "status": anycast_node.status,
        }
        confidence += 0.4

        # 2. 检查地域和业务标签
        if anycast_node.region is not None or anycast_node.site is not None:
            evidence["checks"]["has_geo_info"] = True
            confidence += 0.1
        if anycast_node.business_tag is not None:
            evidence["checks"]["has_business_tag"] = True
            confidence += 0.1

    # 3. 检查历史多 origin 模式
    historical_origins = await _get_historical_origin_asns(db, prefix)
    evidence["checks"]["historical_multi_origin"] = len(historical_origins) > 1
    evidence["historical_origin_asns"] = historical_origins
    if len(historical_origins) > 1:
        confidence += 0.2
        # 当前 origin_as 在历史多 origin 列表中
        if origin_as in historical_origins:
            evidence["checks"]["origin_in_history"] = True
            confidence += 0.1

    # 4. 检查 ASN 关系标签是否标识为 anycast
    asn_meta = await _get_asn_metadata(db, origin_as)
    if asn_meta is not None:
        tags = asn_meta.relationship_tags or []
        if "anycast" in tags:
            evidence["checks"]["asn_tagged_anycast"] = True
            confidence += 0.1

    # 规范化置信度
    confidence = max(0.0, min(1.0, confidence))

    # 判定：已登记 Anycast 节点 → 良性冲突
    is_benign = anycast_node is not None and anycast_node.status == "active"

    if is_benign:
        recommendation = (
            f"前缀 {prefix} 由已登记 Anycast 节点 AS{origin_as} 宣告，"
            "判定为 Anycast 扩容良性冲突。"
            "建议：确认多 origin 授权治理状态，"
            "如需长期多 origin 宣告，建议补齐 ROA 授权或纳入 Anycast 治理流程。"
        )
    elif anycast_node is not None or len(historical_origins) > 1:
        recommendation = (
            f"前缀 {prefix} 由 AS{origin_as} 宣告，存在 Anycast 相关线索"
            "但证据不完整。建议：人工核实 Anycast 节点登记状态与多 origin 授权。"
        )
    else:
        recommendation = "未识别为 Anycast 扩容良性冲突，按正常告警处置流程处理。"

    return BenignConflictAnalysisResult(
        conflict_type="anycast_expansion" if is_benign else None,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
        is_benign=is_benign,
    )


async def _check_anycast_node(
    db: AsyncSession, asn: int, prefix: str
) -> AnycastNode | None:
    """检查是否为已登记的 Anycast 节点。

    Args:
        db: 异步数据库会话
        asn: Anycast 节点 AS 号
        prefix: Anycast 前缀

    Returns:
        Anycast 节点对象（若存在），否则 None
    """
    stmt = (
        select(AnycastNode)
        .where(AnycastNode.node_asn == asn)
        .where(AnycastNode.prefix == prefix)
        .where(AnycastNode.status == "active")
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_historical_origin_asns(
    db: AsyncSession,
    prefix: str,
    lookback_days: int = 30,
) -> list[int]:
    """查询前缀历史上由哪些 AS 宣告过。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        lookback_days: 回溯天数

    Returns:
        历史 origin AS 列表
    """
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    stmt = (
        select(BGPAnnouncement.origin_as)
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as.is_not(None))
        .where(BGPAnnouncement.timestamp >= since)
        .distinct()
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all() if row[0] is not None]


async def _get_asn_metadata(db: AsyncSession, asn: int) -> ASN | None:
    """查询 ASN 元信息。"""
    stmt = select(ASN).where(ASN.asn == asn)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


__all__ = ["detect_anycast_expansion"]
