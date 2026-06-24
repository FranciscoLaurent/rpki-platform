"""源 AS 劫持检测器。

基于 RPKI 验证状态、资产台账、历史基线与传播范围，检测 BGP 公告中的
源 AS 劫持与子前缀劫持。
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.rpki import VRP
from app.schemas.detection import (
    HijackDetectionResult,
    SubprefixHijackResult,
)
from app.services.vrp_service import validate_bgp_announcement

logger = get_logger("app.detection.hijack")


# ──────────────────────────────────────────────
# 源 AS 劫持检测
# ──────────────────────────────────────────────


async def detect_origin_as_hijack(
    db: AsyncSession, announcement: BGPAnnouncement
) -> HijackDetectionResult:
    """检测非授权 origin AS 劫持。

    检测流程：
    1. 关联 RPKI 验证状态：若 Invalid 且 origin_as 不匹配，则为劫持
    2. 关联资产台账：检查 origin_as 是否在授权列表中
    3. 关联历史基线：检查该前缀历史上是否由该 AS 宣告过
    4. 评估传播范围：多少观察点收到该公告

    Args:
        db: 异步数据库会话
        announcement: BGP 公告对象

    Returns:
        劫持检测结果
    """
    prefix = announcement.prefix
    origin_as = announcement.origin_as

    # 缺少 origin_as 无法判定劫持
    if origin_as is None:
        return HijackDetectionResult(
            alert_type="hijack",
            severity="P3",
            description="公告缺少 origin_as，无法判定劫持",
            is_detected=False,
        )

    # 1. RPKI 验证
    rpki_validation = await validate_bgp_announcement(db, prefix, origin_as)
    rpki_status = rpki_validation.validation_result.validation_status
    rpki_invalid_reason = rpki_validation.validation_result.invalid_reason

    # 2. 资产台账检查：查询前缀是否在资产台账中
    authorized_origin_as = await _get_authorized_origin_as(db, prefix)

    # 3. 历史基线：查询该前缀历史上是否由该 AS 宣告过
    historical_origin_asns = await _get_historical_origin_asns(db, prefix)

    # 4. 传播范围：统计多少观察点收到该公告
    propagation_scope = await _count_propagation_scope(db, prefix, origin_as)

    # 判定逻辑
    is_hijack = False
    severity = "P3"
    description = "未检测到劫持"
    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "rpki_validation_status": rpki_status,
        "rpki_invalid_reason": rpki_invalid_reason,
        "authorized_origin_as": authorized_origin_as,
        "historical_origin_asns": historical_origin_asns,
        "propagation_scope": propagation_scope,
    }

    # RPKI Invalid 且 origin_as 不匹配 → 高置信度劫持
    if rpki_status == "invalid" and rpki_invalid_reason in (
        "origin_as_mismatch",
        "length_exceeded",
    ):
        is_hijack = True
        severity = "P0"
        description = (
            f"RPKI 验证失败（{rpki_invalid_reason}），前缀 {prefix} 由 AS{origin_as} 异常宣告"
        )
    # 资产台账中存在授权 origin_as，但公告 origin_as 不在授权列表
    elif (
        authorized_origin_as is not None
        and origin_as != authorized_origin_as
        and origin_as not in historical_origin_asns
    ):
        is_hijack = True
        severity = "P0"
        description = (
            f"前缀 {prefix} 资产台账授权 origin AS 为 AS{authorized_origin_as}，"
            f"但公告由 AS{origin_as} 宣告"
        )
    # 历史上从未由该 AS 宣告，且传播范围广
    elif origin_as not in historical_origin_asns and propagation_scope >= 3:
        is_hijack = True
        severity = "P1"
        description = (
            f"前缀 {prefix} 历史上从未由 AS{origin_as} 宣告，"
            f"当前已被 {propagation_scope} 个观察点接收"
        )

    # 传播范围扩大风险
    if is_hijack and propagation_scope >= 10:
        severity = "P0"

    return HijackDetectionResult(
        alert_type="hijack",
        severity=severity,
        description=description,
        evidence=evidence,
        is_detected=is_hijack,
        authorized_origin_as=authorized_origin_as,
        detected_origin_as=origin_as,
        rpki_validation_status=rpki_status,
        propagation_scope=propagation_scope,
        risk_score=0.0,  # 由 risk_scorer 计算
        confidence=0.9 if rpki_status == "invalid" else 0.6,
    )


async def _get_authorized_origin_as(db: AsyncSession, prefix: str) -> int | None:
    """从资产台账查询前缀的授权 origin AS。

    通过 Prefix 表的 customer_id 关联与 VRP 表查询授权 origin AS。
    简化实现：查询覆盖该前缀的有效 VRP，返回最常见的 origin_as。
    """
    try:
        network = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return None

    # 查询覆盖该前缀的所有有效 VRP
    stmt = (
        select(VRP.origin_as, func.count(VRP.id).label("cnt"))
        .where(VRP.validation_status == "valid")
        .where(VRP.prefix_length <= network.prefixlen)
        .group_by(VRP.origin_as)
        .order_by(func.count(VRP.id).desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return row.origin_as


async def _get_historical_origin_asns(
    db: AsyncSession, prefix: str, lookback_days: int = 30
) -> list[int]:
    """查询前缀历史上由哪些 AS 宣告过。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        lookback_days: 回溯天数

    Returns:
        历史 origin AS 列表
    """
    since = datetime.now(UTC) - timedelta(days=lookback_days)
    stmt = (
        select(BGPAnnouncement.origin_as)
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as.is_not(None))
        .where(BGPAnnouncement.timestamp >= since)
        .distinct()
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all() if row[0] is not None]


async def _count_propagation_scope(db: AsyncSession, prefix: str, origin_as: int) -> int:
    """统计多少观察点收到该前缀+origin_as 的公告。"""
    stmt = (
        select(func.count(func.distinct(BGPAnnouncement.observation_point_id)))
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as == origin_as)
    )
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


# ──────────────────────────────────────────────
# 子前缀劫持检测
# ──────────────────────────────────────────────


async def detect_subprefix_hijack(
    db: AsyncSession, announcement: BGPAnnouncement
) -> SubprefixHijackResult:
    """子前缀劫持检测。

    检测更具体前缀的异常公告，评估流量吸引风险，检查 ROA/maxLength 漏洞。

    Args:
        db: 异步数据库会话
        announcement: BGP 公告对象

    Returns:
        子前缀劫持检测结果
    """
    prefix = announcement.prefix
    origin_as = announcement.origin_as

    if origin_as is None:
        return SubprefixHijackResult(
            alert_type="subprefix_hijack",
            severity="P3",
            description="公告缺少 origin_as，无法判定子前缀劫持",
            is_detected=False,
        )

    try:
        network = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return SubprefixHijackResult(
            alert_type="subprefix_hijack",
            severity="P3",
            description=f"无效前缀 {prefix}",
            is_detected=False,
        )

    # 查询覆盖该前缀的所有 VRP（祖先链）
    parent_vrps = await _find_covering_vrps(db, prefix)

    if not parent_vrps:
        return SubprefixHijackResult(
            alert_type="subprefix_hijack",
            severity="P3",
            description=f"前缀 {prefix} 无覆盖 VRP，无法判定子前缀劫持",
            is_detected=False,
        )

    # 检查每个父 VRP：是否允许该 origin_as、是否超过 maxLength
    is_hijack = False
    severity = "P3"
    description = "未检测到子前缀劫持"
    parent_prefix = None
    max_length_allowed = None
    traffic_risk = "low"

    for vrp in parent_vrps:
        # 父 VRP 与公告前缀不同（即公告是更具体前缀）
        if vrp.prefix == prefix:
            continue

        parent_prefix = vrp.prefix
        max_length_allowed = vrp.max_length or vrp.prefix_length

        # origin_as 不匹配 + 前缀长度超过 maxLength → 子前缀劫持
        if vrp.origin_as != origin_as:
            is_hijack = True
            severity = "P0"
            description = (
                f"子前缀 {prefix} 由 AS{origin_as} 宣告，"
                f"但父前缀 {parent_prefix} 授权 AS{vrp.origin_as}"
            )
            traffic_risk = "high"
            break

        # origin_as 匹配但前缀长度超过 maxLength → maxLength 漏洞利用
        if network.prefixlen > max_length_allowed:
            is_hijack = True
            severity = "P1"
            description = (
                f"子前缀 {prefix} 长度 {network.prefixlen} 超过 "
                f"VRP maxLength {max_length_allowed}（父前缀 {parent_prefix}）"
            )
            traffic_risk = "medium"
            break

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "parent_prefix": parent_prefix,
        "max_length_allowed": max_length_allowed,
        "parent_vrps": [
            {
                "prefix": vrp.prefix,
                "origin_as": vrp.origin_as,
                "max_length": vrp.max_length,
            }
            for vrp in parent_vrps
        ],
    }

    return SubprefixHijackResult(
        alert_type="subprefix_hijack",
        severity=severity,
        description=description,
        evidence=evidence,
        is_detected=is_hijack,
        parent_prefix=parent_prefix,
        subprefix=prefix,
        max_length_allowed=max_length_allowed,
        traffic_attraction_risk=traffic_risk,
        risk_score=0.0,
        confidence=0.85 if is_hijack else 0.5,
    )


async def _find_covering_vrps(db: AsyncSession, prefix: str) -> list[VRP]:
    """查询覆盖指定前缀的所有有效 VRP。

    通过逐级构建祖先前缀列表进行精确匹配查询。
    """
    try:
        network = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return []

    # 构建覆盖前缀链
    covering: list[str] = []
    for length in range(0, network.prefixlen + 1):
        addr_int = int(network.network_address)
        if network.version == 4:
            if length == 0:
                mask = 0
            else:
                mask = (0xFFFFFFFF << (32 - length)) & 0xFFFFFFFF
            parent_addr = addr_int & mask
            parent = ipaddress.IPv4Network((parent_addr, length), strict=True)
        else:
            if length == 0:
                mask = 0
            else:
                mask = (1 << 128) - (1 << (128 - length))
            parent_addr = addr_int & mask
            parent = ipaddress.IPv6Network((parent_addr, length), strict=True)
        covering.append(str(parent))

    stmt = (
        select(VRP)
        .where(VRP.validation_status == "valid")
        .where(VRP.prefix.in_(covering))
        .order_by(VRP.prefix_length.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


__all__ = [
    "detect_origin_as_hijack",
    "detect_subprefix_hijack",
]
