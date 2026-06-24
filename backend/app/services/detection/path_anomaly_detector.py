"""路径异常检测器。

检测 AS_PATH 突变、异常中转 ASN、异常国家/区域传播、路径异常拉长与
黑洞风险等异常情况。
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement
from app.schemas.detection import PathAnomalyResult

logger = get_logger("app.detection.path_anomaly")


async def detect_path_anomaly(db: AsyncSession, announcement: BGPAnnouncement) -> PathAnomalyResult:
    """路径异常检测。

    检测流程：
    1. AS_PATH 突变检测（与历史基线对比）
    2. 异常中转 ASN 检测
    3. 异常国家/区域传播检测（占位，需要 GeoIP）
    4. 路径异常拉长检测
    5. 黑洞风险检测

    Args:
        db: 异步数据库会话
        announcement: BGP 公告对象

    Returns:
        路径异常检测结果
    """
    as_path = announcement.as_path
    prefix = announcement.prefix

    if not as_path:
        return PathAnomalyResult(
            alert_type="path_anomaly",
            severity="P3",
            description="公告缺少 AS_PATH，无法判定路径异常",
            is_detected=False,
            confidence=0.5,
        )

    # 1. 历史基线对比
    baseline_path = await _get_baseline_path(db, prefix)
    path_mutation = _detect_path_mutation(as_path, baseline_path)

    # 2. 异常中转 ASN 检测
    asn_meta = await _get_asn_metadata(db, as_path)
    abnormal_transit = _detect_abnormal_transit(as_path, asn_meta)

    # 3. 路径异常拉长检测
    path_elongation = _detect_path_elongation(as_path, baseline_path)

    # 4. 黑洞风险检测
    blackhole_risk = _detect_blackhole_risk(as_path, asn_meta)

    # 5. 异常国家/区域传播检测（占位）
    abnormal_geo = await _detect_abnormal_geo(as_path)

    # 综合判定
    anomalies = []
    severity = "P3"
    description = "未检测到路径异常"

    if path_mutation["is_anomaly"]:
        anomalies.append("path_mutation")
        severity = "P2"
        description = path_mutation["description"]

    if abnormal_transit["is_anomaly"]:
        anomalies.append("abnormal_transit")
        if severity == "P3":
            severity = "P2"
            description = abnormal_transit["description"]

    if path_elongation["is_anomaly"]:
        anomalies.append("path_elongation")
        if severity == "P3":
            severity = "P2"
            description = path_elongation["description"]

    if blackhole_risk["is_anomaly"]:
        anomalies.append("blackhole_risk")
        severity = "P1"
        description = blackhole_risk["description"]

    if abnormal_geo.get("is_anomaly"):
        anomalies.append("abnormal_geo")
        if severity == "P3":
            severity = "P2"
            description = abnormal_geo["description"]

    is_anomaly = len(anomalies) > 0
    anomaly_type = anomalies[0] if anomalies else None

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "as_path": as_path,
        "baseline_path": baseline_path,
        "path_mutation": path_mutation,
        "abnormal_transit": abnormal_transit,
        "path_elongation": path_elongation,
        "blackhole_risk": blackhole_risk,
        "abnormal_geo": abnormal_geo,
    }

    return PathAnomalyResult(
        alert_type="path_anomaly",
        severity=severity,
        description=description,
        evidence=evidence,
        anomaly_type=anomaly_type,
        baseline_path=baseline_path,
        observed_path=as_path,
        is_detected=is_anomaly,
        risk_score=0.0,
        confidence=0.7 if is_anomaly else 0.5,
    )


async def _get_baseline_path(
    db: AsyncSession,
    prefix: str,
    lookback_days: int = 7,
) -> list[int] | None:
    """获取前缀的历史基线 AS_PATH（最常见路径）。"""
    since = datetime.now(UTC) - timedelta(days=lookback_days)
    # 查询近期该前缀的所有 AS_PATH
    stmt = (
        select(BGPAnnouncement.as_path)
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.as_path.is_not(None))
        .where(BGPAnnouncement.timestamp >= since)
    )
    result = await db.execute(stmt)
    paths = [tuple(row[0]) for row in result.all() if row[0]]

    if not paths:
        return None

    # 取最常见的路径作为基线
    counter = Counter(paths)
    most_common = counter.most_common(1)[0][0]
    return list(most_common)


async def _get_asn_metadata(db: AsyncSession, asn_list: list[int]) -> dict[int, dict[str, Any]]:
    """查询 ASN 元信息。"""
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
            "risk_profile": asn.risk_profile,
        }
        for asn in asn_objects
    }


def _detect_path_mutation(
    current_path: list[int],
    baseline_path: list[int] | None,
) -> dict[str, Any]:
    """检测 AS_PATH 突变。

    与历史基线对比，识别路径中新增或缺失的 AS。
    """
    if baseline_path is None:
        return {
            "is_anomaly": False,
            "description": "无历史基线，无法判定路径突变",
            "added_asns": [],
            "removed_asns": [],
        }

    current_set = set(current_path)
    baseline_set = set(baseline_path)
    added = current_set - baseline_set
    removed = baseline_set - current_set

    # 路径完全不同（除 origin 外几乎全部变化）
    if len(added) >= 2 and len(current_set) >= 3:
        return {
            "is_anomaly": True,
            "description": (f"AS_PATH 突变：新增 AS {sorted(added)}，移除 AS {sorted(removed)}"),
            "added_asns": sorted(added),
            "removed_asns": sorted(removed),
        }

    return {
        "is_anomaly": False,
        "description": "AS_PATH 与基线一致或变化较小",
        "added_asns": sorted(added),
        "removed_asns": sorted(removed),
    }


def _detect_abnormal_transit(
    as_path: list[int],
    asn_meta: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """检测异常中转 ASN。

    识别路径中出现的非中转类型 AS（如 IXP、route_server）作为中转，
    或风险画像标注为高风险的 AS。
    """
    abnormal_asns: list[int] = []
    # 路径中间的 AS（非首尾）应为中转 AS
    for asn in as_path[1:-1]:
        meta = asn_meta.get(asn)
        if meta is None:
            # 未知 AS 作为中转
            abnormal_asns.append(asn)
            continue
        asn_type = meta.get("asn_type", "unknown")
        risk_profile = meta.get("risk_profile")
        # IXP/route_server 不应作为中转
        if (
            asn_type in ("ixp", "route_server")
            or risk_profile
            and "high_risk" in risk_profile.lower()
        ):
            abnormal_asns.append(asn)

    if abnormal_asns:
        return {
            "is_anomaly": True,
            "description": (f"AS_PATH 中出现异常中转 AS：{abnormal_asns}"),
            "abnormal_asns": abnormal_asns,
        }

    return {
        "is_anomaly": False,
        "description": "未检测到异常中转 AS",
        "abnormal_asns": [],
    }


def _detect_path_elongation(
    current_path: list[int],
    baseline_path: list[int] | None,
) -> dict[str, Any]:
    """检测路径异常拉长。"""
    if baseline_path is None:
        return {
            "is_anomaly": False,
            "description": "无历史基线，无法判定路径拉长",
            "current_length": len(current_path),
            "baseline_length": None,
        }

    current_len = len(current_path)
    baseline_len = len(baseline_path)

    # 路径长度超过基线 2 倍且绝对长度 >= 5
    if baseline_len > 0 and current_len >= baseline_len * 2 and current_len >= 5:
        return {
            "is_anomaly": True,
            "description": (f"AS_PATH 异常拉长：当前 {current_len} 跳，基线 {baseline_len} 跳"),
            "current_length": current_len,
            "baseline_length": baseline_len,
        }

    return {
        "is_anomaly": False,
        "description": "AS_PATH 长度正常",
        "current_length": current_len,
        "baseline_length": baseline_len,
    }


def _detect_blackhole_risk(
    as_path: list[int],
    asn_meta: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """检测黑洞风险。

    当路径中出现高风险 AS 或路径异常短（可能被劫持后丢弃流量）时，
    判定为黑洞风险。
    """
    # 路径异常短（仅 1 跳）且 origin AS 风险画像异常
    if len(as_path) == 1:
        origin_asn = as_path[0]
        meta = asn_meta.get(origin_asn)
        if meta and meta.get("risk_profile"):
            risk = meta["risk_profile"].lower()
            if "blackhole" in risk or "high_risk" in risk:
                return {
                    "is_anomaly": True,
                    "description": (f"黑洞风险：路径仅 1 跳且 origin AS{origin_asn} 风险画像异常"),
                    "risk_asns": [origin_asn],
                }

    return {
        "is_anomaly": False,
        "description": "未检测到黑洞风险",
        "risk_asns": [],
    }


async def _detect_abnormal_geo(as_path: list[int]) -> dict[str, Any]:
    """异常国家/区域传播检测（占位，需要 GeoIP）。

    TODO: 接入 GeoIP 数据库后实现：
    1. 将 AS_PATH 中的 AS 映射到注册国家
    2. 识别异常的跨区域传播（如流量绕道异常国家）
    """
    return {
        "is_anomaly": False,
        "description": "异常国家/区域传播检测为占位实现，需要 GeoIP 数据",
        "checked": False,
    }


__all__ = ["detect_path_anomaly"]
