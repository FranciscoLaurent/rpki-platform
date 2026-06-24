"""自动取证服务（Task 20 简化接口）。

提供事件级别的自动取证能力，将采集到的 ROA/VRP、BGP 样本、AS_PATH、
传播范围、观察点、资产关系、变更记录与历史基线等证据汇总为字典，
存入 ``Incident.evidence`` JSON 字段，并在 ``Incident.timeline`` 追加取证记录。

本模块与已有的 ``app.services.forensic_service`` 互补：
- ``forensic_service`` 提供细粒度的取证证据 CRUD 与逐条证据持久化
- 本模块提供事件级别的取证汇总接口，便于端点直接调用
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement, BGPWithdraw, ObservationPoint
from app.models.business import BusinessService, Customer
from app.models.detection import Alert, Incident
from app.models.prefix import Prefix
from app.models.rpki import ROA, VRP

logger = get_logger("app.forensics_service")


# 取证采集时间窗口（事件前后各 1 小时）
EVIDENCE_WINDOW_BEFORE = timedelta(hours=1)
EVIDENCE_WINDOW_AFTER = timedelta(hours=1)
# 历史基线窗口（30 天）
HISTORICAL_BASELINE_DAYS = 30
# 每类证据采集上限
SAMPLE_LIMIT = 50


async def collect_evidence(
    db: AsyncSession,
    incident_id: int,
    collected_by: int | None = None,
) -> dict[str, Any]:
    """采集事件关联的全部取证证据并汇总为字典。

    采集内容包括：
    - ROA/VRP 授权快照
    - BGP 公告样本（含 AS_PATH、origin AS、前缀）
    - 传播范围与观察点分布
    - 观察点信息
    - 资产关系（前缀、ASN、客户、业务服务）
    - 变更记录（占位）
    - 历史基线（30 天内的 origin AS 历史）

    采集结果会写入 ``Incident.evidence`` JSON 字段，并在
    ``Incident.timeline`` 追加一条取证记录。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID
        collected_by: 采集人用户 ID（自动采集为空）

    Returns:
        取证结果字典，结构同 ``EvidenceCollection`` 模式
    """
    now = datetime.now(UTC)

    # 查询事件
    incident = await _get_incident(db, incident_id)
    if incident is None:
        logger.warning("取证失败：事件不存在", incident_id=incident_id)
        return {
            "incident_id": incident_id,
            "collected_at": now.isoformat(),
            "collected_by": collected_by,
            "evidence_count": 0,
            "evidence_by_type": {},
            "roa_vrp": [],
            "bgp_samples": [],
            "as_paths": [],
            "propagation_scope": {},
            "observation_points": [],
            "asset_relations": [],
            "change_records": [],
            "historical_baseline": [],
            "errors": [f"事件 ID {incident_id} 不存在"],
        }

    # 收集受影响前缀与 ASN
    prefixes = list(incident.affected_prefixes or [])
    asns = list(incident.affected_asns or [])

    # 从关联告警补充前缀与 ASN
    alerts = await _get_incident_alerts(db, incident_id)
    for alert in alerts:
        if alert.prefix and alert.prefix not in prefixes:
            prefixes.append(alert.prefix)
        if alert.origin_as and alert.origin_as not in asns:
            asns.append(alert.origin_as)

    # 确定采集时间窗口
    center_time = incident.first_seen_at or incident.created_at or now
    window_start = center_time - EVIDENCE_WINDOW_BEFORE
    window_end = center_time + EVIDENCE_WINDOW_AFTER

    errors: list[str] = []
    evidence_by_type: dict[str, int] = {}

    # 1. 采集 ROA/VRP 授权快照
    try:
        roa_vrp = await _collect_roa_vrp(db, prefixes)
        evidence_by_type["roa_vrp"] = len(roa_vrp)
    except Exception as e:
        roa_vrp = []
        errors.append(f"采集 ROA/VRP 证据失败：{e}")
        logger.exception("采集 ROA/VRP 证据失败", incident_id=incident_id)

    # 2. 采集 BGP 公告样本
    try:
        bgp_samples = await _collect_bgp_samples(db, prefixes, window_start, window_end)
        evidence_by_type["bgp_sample"] = len(bgp_samples)
    except Exception as e:
        bgp_samples = []
        errors.append(f"采集 BGP 样本证据失败：{e}")
        logger.exception("采集 BGP 样本证据失败", incident_id=incident_id)

    # 3. 采集 AS_PATH 路径
    try:
        as_paths = await _collect_as_paths(db, prefixes, window_start, window_end)
        evidence_by_type["as_path"] = len(as_paths)
    except Exception as e:
        as_paths = []
        errors.append(f"采集 AS_PATH 证据失败：{e}")
        logger.exception("采集 AS_PATH 证据失败", incident_id=incident_id)

    # 4. 采集传播范围
    try:
        propagation_scope = await _collect_propagation_scope(db, prefixes, window_start, window_end)
        evidence_by_type["propagation_scope"] = len(propagation_scope.get("observation_points", []))
    except Exception as e:
        propagation_scope = {}
        errors.append(f"采集传播范围证据失败：{e}")
        logger.exception("采集传播范围证据失败", incident_id=incident_id)

    # 5. 采集观察点信息
    try:
        observation_points = await _collect_observation_points(db)
        evidence_by_type["observation_point"] = len(observation_points)
    except Exception as e:
        observation_points = []
        errors.append(f"采集观察点证据失败：{e}")
        logger.exception("采集观察点证据失败", incident_id=incident_id)

    # 6. 采集资产关系
    try:
        asset_relations = await _collect_asset_relations(db, prefixes, asns)
        evidence_by_type["asset_relation"] = len(asset_relations)
    except Exception as e:
        asset_relations = []
        errors.append(f"采集资产关系证据失败：{e}")
        logger.exception("采集资产关系证据失败", incident_id=incident_id)

    # 7. 采集变更记录（占位）
    change_records: list[dict[str, Any]] = []
    evidence_by_type["change_record"] = 0

    # 8. 采集历史基线
    try:
        historical_baseline = await _collect_historical_baseline(db, prefixes, now)
        evidence_by_type["historical_baseline"] = len(historical_baseline)
    except Exception as e:
        historical_baseline = []
        errors.append(f"采集历史基线证据失败：{e}")
        logger.exception("采集历史基线证据失败", incident_id=incident_id)

    # 汇总证据
    evidence: dict[str, Any] = {
        "incident_id": incident_id,
        "collected_at": now.isoformat(),
        "collected_by": collected_by,
        "evidence_count": sum(evidence_by_type.values()),
        "evidence_by_type": evidence_by_type,
        "roa_vrp": roa_vrp,
        "bgp_samples": bgp_samples,
        "as_paths": as_paths,
        "propagation_scope": propagation_scope,
        "observation_points": observation_points,
        "asset_relations": asset_relations,
        "change_records": change_records,
        "historical_baseline": historical_baseline,
        "errors": errors,
    }

    # 将证据存入 Incident.evidence JSON 字段
    incident.evidence = evidence

    # 在 Incident.timeline 追加取证记录
    timeline = incident.timeline or []
    timeline.append(
        {
            "timestamp": now.isoformat(),
            "event_type": "evidence_collected",
            "description": (f"自动取证完成，共采集 {evidence['evidence_count']} 条证据"),
            "operator": collected_by,
        }
    )
    incident.timeline = timeline
    incident.last_seen_at = now

    await db.flush()

    logger.info(
        "自动取证完成",
        incident_id=incident_id,
        evidence_count=evidence["evidence_count"],
        error_count=len(errors),
    )
    return evidence


# ──────────────────────────────────────────────
# 各类证据采集器
# ──────────────────────────────────────────────


async def _collect_roa_vrp(db: AsyncSession, prefixes: list[str]) -> list[dict[str, Any]]:
    """采集 ROA/VRP 授权快照。"""
    results: list[dict[str, Any]] = []
    for prefix in prefixes:
        # 查询 VRP
        vrp_stmt = select(VRP).where(VRP.prefix == prefix)
        vrp_result = await db.execute(vrp_stmt)
        vrps = list(vrp_result.scalars().all())

        # 查询 ROA
        roa_stmt = select(ROA).where(ROA.prefix == prefix)
        roa_result = await db.execute(roa_stmt)
        roas = list(roa_result.scalars().all())

        if not vrps and not roas:
            continue

        results.append(
            {
                "prefix": prefix,
                "vrps": [
                    {
                        "id": v.id,
                        "prefix": v.prefix,
                        "origin_as": v.origin_as,
                        "max_length": v.max_length,
                        "validation_status": getattr(v, "validation_status", None),
                    }
                    for v in vrps
                ],
                "roas": [
                    {
                        "id": r.id,
                        "prefix": r.prefix,
                        "origin_as": r.origin_as,
                        "max_length": r.max_length,
                        "status": r.status,
                    }
                    for r in roas
                ],
            }
        )
    return results


async def _collect_bgp_samples(
    db: AsyncSession,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    """采集 BGP 公告与撤路样本。"""
    results: list[dict[str, Any]] = []
    for prefix in prefixes:
        # 公告样本
        ann_stmt = (
            select(BGPAnnouncement)
            .where(BGPAnnouncement.prefix == prefix)
            .where(BGPAnnouncement.timestamp >= window_start)
            .where(BGPAnnouncement.timestamp <= window_end)
            .order_by(BGPAnnouncement.timestamp.desc())
            .limit(SAMPLE_LIMIT)
        )
        ann_result = await db.execute(ann_stmt)
        announcements = list(ann_result.scalars().all())

        # 撤路样本
        wd_stmt = (
            select(BGPWithdraw)
            .where(BGPWithdraw.prefix == prefix)
            .where(BGPWithdraw.timestamp >= window_start)
            .where(BGPWithdraw.timestamp <= window_end)
            .order_by(BGPWithdraw.timestamp.desc())
            .limit(SAMPLE_LIMIT)
        )
        wd_result = await db.execute(wd_stmt)
        withdraws = list(wd_result.scalars().all())

        if not announcements and not withdraws:
            continue

        results.append(
            {
                "prefix": prefix,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "announcement_count": len(announcements),
                "withdraw_count": len(withdraws),
                "announcements": [
                    {
                        "id": a.id,
                        "origin_as": a.origin_as,
                        "as_path": a.as_path,
                        "observation_point_id": a.observation_point_id,
                        "rpki_validation_status": a.rpki_validation_status,
                        "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                    }
                    for a in announcements[:20]
                ],
                "withdraws": [
                    {
                        "id": w.id,
                        "observation_point_id": w.observation_point_id,
                        "timestamp": w.timestamp.isoformat() if w.timestamp else None,
                    }
                    for w in withdraws[:20]
                ],
            }
        )
    return results


async def _collect_as_paths(
    db: AsyncSession,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    """采集 AS_PATH 路径样本。"""
    results: list[dict[str, Any]] = []
    for prefix in prefixes:
        ann_stmt = (
            select(BGPAnnouncement.as_path, BGPAnnouncement.origin_as)
            .where(BGPAnnouncement.prefix == prefix)
            .where(BGPAnnouncement.timestamp >= window_start)
            .where(BGPAnnouncement.timestamp <= window_end)
            .where(BGPAnnouncement.as_path.is_not(None))
            .distinct()
            .limit(100)
        )
        result = await db.execute(ann_stmt)
        rows = result.all()

        if not rows:
            continue

        paths: list[dict[str, Any]] = []
        unique_paths: set[tuple[int, ...]] = set()
        for row in rows:
            as_path = row[0]
            origin_as = row[1]
            path_key = tuple(as_path) if as_path else ()
            if path_key in unique_paths:
                continue
            unique_paths.add(path_key)
            paths.append(
                {
                    "as_path": as_path,
                    "origin_as": origin_as,
                    "path_length": len(as_path) if as_path else 0,
                }
            )

        results.append(
            {
                "prefix": prefix,
                "unique_path_count": len(paths),
                "paths": paths[:50],
            }
        )
    return results


async def _collect_propagation_scope(
    db: AsyncSession,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    """采集传播范围（观察点分布）。"""
    all_observation_points: list[dict[str, Any]] = []
    total_scope = 0
    for prefix in prefixes:
        ann_stmt = (
            select(
                BGPAnnouncement.observation_point_id,
                func.count(BGPAnnouncement.id),
            )
            .where(BGPAnnouncement.prefix == prefix)
            .where(BGPAnnouncement.timestamp >= window_start)
            .where(BGPAnnouncement.timestamp <= window_end)
            .group_by(BGPAnnouncement.observation_point_id)
        )
        result = await db.execute(ann_stmt)
        rows = result.all()

        for row in rows:
            all_observation_points.append(
                {
                    "prefix": prefix,
                    "observation_point_id": row[0],
                    "announcement_count": int(row[1]),
                }
            )
            total_scope += 1

    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "total_observation_count": total_scope,
        "observation_points": all_observation_points,
    }


async def _collect_observation_points(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """采集活跃观察点信息。"""
    stmt = select(ObservationPoint).where(ObservationPoint.status == "active")
    result = await db.execute(stmt)
    observation_points = list(result.scalars().all())

    return [
        {
            "id": op.id,
            "name": op.name,
            "location": op.location,
            "collector_id": op.collector_id,
            "ip_version": op.ip_version,
        }
        for op in observation_points
    ]


async def _collect_asset_relations(
    db: AsyncSession,
    prefixes: list[str],
    asns: list[int],
) -> list[dict[str, Any]]:
    """采集资产关系（前缀、客户、业务服务、ASN）。"""
    results: list[dict[str, Any]] = []

    # 前缀资产关系
    for prefix in prefixes:
        stmt = select(Prefix).where(Prefix.prefix == prefix)
        result = await db.execute(stmt)
        prefix_obj = result.scalar_one_or_none()
        if prefix_obj is None:
            continue

        asset_info: dict[str, Any] = {
            "type": "prefix",
            "prefix": prefix_obj.prefix,
            "importance": prefix_obj.importance,
            "status": prefix_obj.status,
            "customer_id": prefix_obj.customer_id,
            "business_service": prefix_obj.business_service,
        }

        # 关联客户
        if prefix_obj.customer_id is not None:
            cust_stmt = select(Customer).where(Customer.id == prefix_obj.customer_id)
            cust_result = await db.execute(cust_stmt)
            customer = cust_result.scalar_one_or_none()
            if customer:
                asset_info["customer"] = {
                    "id": customer.id,
                    "name": customer.name,
                    "service_level": customer.service_level,
                }

        # 关联业务服务
        if prefix_obj.business_service:
            biz_stmt = select(BusinessService).where(
                BusinessService.name == prefix_obj.business_service
            )
            biz_result = await db.execute(biz_stmt)
            biz = biz_result.scalar_one_or_none()
            if biz:
                asset_info["business_service_info"] = {
                    "id": biz.id,
                    "name": biz.name,
                    "importance": biz.importance,
                }

        results.append(asset_info)

    # ASN 资产关系
    for asn in asns:
        stmt = select(ASN).where(ASN.asn == asn)
        result = await db.execute(stmt)
        asn_obj = result.scalar_one_or_none()
        if asn_obj is None:
            continue
        results.append(
            {
                "type": "asn",
                "asn": asn_obj.asn,
                "name": asn_obj.name,
                "asn_type": asn_obj.asn_type,
                "risk_profile": asn_obj.risk_profile,
                "contact_email": asn_obj.contact_email,
                "noc_phone": asn_obj.noc_phone,
            }
        )

    return results


async def _collect_historical_baseline(
    db: AsyncSession,
    prefixes: list[str],
    now: datetime,
) -> list[dict[str, Any]]:
    """采集历史基线（30 天内的 origin AS 历史）。"""
    results: list[dict[str, Any]] = []
    since = now - timedelta(days=HISTORICAL_BASELINE_DAYS)

    for prefix in prefixes:
        stmt = (
            select(
                BGPAnnouncement.origin_as,
                func.count(BGPAnnouncement.id),
                func.min(BGPAnnouncement.timestamp),
                func.max(BGPAnnouncement.timestamp),
            )
            .where(BGPAnnouncement.prefix == prefix)
            .where(BGPAnnouncement.origin_as.is_not(None))
            .where(BGPAnnouncement.timestamp >= since)
            .group_by(BGPAnnouncement.origin_as)
            .order_by(func.count(BGPAnnouncement.id).desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            continue

        historical_origins = [
            {
                "origin_as": row[0],
                "announcement_count": int(row[1]),
                "first_seen": row[2].isoformat() if row[2] else None,
                "last_seen": row[3].isoformat() if row[3] else None,
            }
            for row in rows
        ]

        results.append(
            {
                "prefix": prefix,
                "baseline_window_days": HISTORICAL_BASELINE_DAYS,
                "historical_origin_asns": historical_origins,
                "unique_origin_count": len(historical_origins),
                "is_moas": len(historical_origins) >= 2,
            }
        )

    return results


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _get_incident(db: AsyncSession, incident_id: int) -> Incident | None:
    """获取事件。"""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_incident_alerts(db: AsyncSession, incident_id: int) -> list[Alert]:
    """获取事件关联的告警。"""
    stmt = select(Alert).where(Alert.incident_id == incident_id).order_by(Alert.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


__all__ = ["collect_evidence"]
