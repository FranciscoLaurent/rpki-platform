"""自动取证服务。

提供事件/告警的自动取证能力，采集 ROA/VRP、BGP 样本、AS_PATH、传播范围、
观察点、资产关系、变更记录与历史基线等多类证据，并持久化为取证证据记录。

取证原则：
- 证据采集应在事件触发后尽快完成，避免数据漂移
- 证据内容以快照形式存储，确保可回溯
- 自动采集的证据标记 ``is_auto_collected=True``
- 证据完整性哈希用于防篡改校验（占位实现）
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import (
    BGPAnnouncement,
    BGPWithdraw,
    ObservationPoint,
)
from app.models.business import BusinessService, Customer
from app.models.detection import Alert, Incident
from app.models.forensics import ForensicEvidence
from app.models.prefix import Prefix
from app.models.rpki import ROA, VRP
from app.schemas.forensics import (
    ForensicCollectionRequest,
    ForensicCollectionResult,
    ForensicEvidenceCreate,
    ForensicEvidenceQueryParams,
)

logger = get_logger("app.forensic_service")


# 证据采集时间窗口（事件前后各 1 小时）
EVIDENCE_WINDOW_BEFORE = timedelta(hours=1)
EVIDENCE_WINDOW_AFTER = timedelta(hours=1)


async def collect_forensic_evidence(
    db: AsyncSession,
    request: ForensicCollectionRequest,
    collected_by: int | None = None,
) -> ForensicCollectionResult:
    """自动采集取证证据。

    根据请求采集指定事件或告警的多类证据，包括：
    - ROA/VRP 授权信息
    - BGP 公告与撤路样本
    - AS_PATH 路径
    - 传播范围（观察点分布）
    - 观察点信息
    - 资产关系（前缀、客户、业务服务）
    - 变更记录（占位）
    - 历史基线（30 天内的 origin AS 历史）

    Args:
        db: 异步数据库会话
        request: 取证采集请求
        collected_by: 采集人用户 ID（自动采集为空）

    Returns:
        取证采集结果
    """
    result = ForensicCollectionResult(
        incident_id=request.incident_id,
        alert_id=request.alert_id,
    )

    # 确定采集目标（事件或告警）
    incident: Incident | None = None
    alert: Alert | None = None
    prefixes: list[str] = []
    asns: list[int] = []

    if request.incident_id is not None:
        incident = await _get_incident(db, request.incident_id)
        if incident is None:
            result.errors.append(f"事件 ID {request.incident_id} 不存在")
            return result
        prefixes = list(incident.affected_prefixes or [])
        asns = list(incident.affected_asns or [])
        # 从事件的 alert_ids 补充前缀与 ASN
        if incident.alert_ids:
            for aid in incident.alert_ids:
                a = await _get_alert(db, aid)
                if a is not None:
                    if a.prefix and a.prefix not in prefixes:
                        prefixes.append(a.prefix)
                    if a.origin_as and a.origin_as not in asns:
                        asns.append(a.origin_as)
    elif request.alert_id is not None:
        alert = await _get_alert(db, request.alert_id)
        if alert is None:
            result.errors.append(f"告警 ID {request.alert_id} 不存在")
            return result
        prefixes = [alert.prefix] if alert.prefix else []
        asns = [alert.origin_as] if alert.origin_as else []

    if not prefixes:
        result.errors.append("无可采集的前缀，取证终止")
        return result

    # 确定采集时间窗口
    if incident is not None:
        center_time = incident.first_seen_at or incident.created_at
    elif alert is not None:
        center_time = alert.first_seen_at or alert.created_at
    else:
        center_time = datetime.now(UTC)

    window_start = center_time - EVIDENCE_WINDOW_BEFORE
    window_end = center_time + EVIDENCE_WINDOW_AFTER

    # 确定要采集的证据类型
    target_types = request.evidence_types or list(
        {
            "roa_vrp",
            "bgp_sample",
            "as_path",
            "propagation_scope",
            "observation_point",
            "asset_relation",
            "change_record",
            "historical_baseline",
        }
    )

    # 按类型采集证据
    for evidence_type in target_types:
        try:
            if evidence_type == "roa_vrp":
                count = await _collect_roa_vrp_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    asns,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "bgp_sample":
                count = await _collect_bgp_sample_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    window_start,
                    window_end,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "as_path":
                count = await _collect_as_path_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    window_start,
                    window_end,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "propagation_scope":
                count = await _collect_propagation_scope_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    window_start,
                    window_end,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "observation_point":
                count = await _collect_observation_point_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    window_start,
                    window_end,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "asset_relation":
                count = await _collect_asset_relation_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    asns,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "change_record":
                count = await _collect_change_record_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    asns,
                    center_time,
                    collected_by,
                )
            elif evidence_type == "historical_baseline":
                count = await _collect_historical_baseline_evidence(
                    db,
                    request.incident_id,
                    request.alert_id,
                    prefixes,
                    asns,
                    center_time,
                    collected_by,
                )
            else:
                result.errors.append(f"不支持的证据类型：{evidence_type}")
                continue

            result.evidence_by_type[evidence_type] = count
            result.collected_count += count
        except Exception as e:
            logger.exception(
                "采集证据失败",
                evidence_type=evidence_type,
                error=str(e),
            )
            result.errors.append(f"采集 {evidence_type} 证据失败：{e}")

    logger.info(
        "自动取证完成",
        incident_id=request.incident_id,
        alert_id=request.alert_id,
        collected_count=result.collected_count,
    )
    return result


# ──────────────────────────────────────────────
# 取证证据 CRUD
# ──────────────────────────────────────────────


async def create_evidence(
    db: AsyncSession, evidence_data: ForensicEvidenceCreate
) -> ForensicEvidence:
    """创建取证证据记录。"""
    evidence = ForensicEvidence(
        incident_id=evidence_data.incident_id,
        alert_id=evidence_data.alert_id,
        evidence_type=evidence_data.evidence_type,
        title=evidence_data.title,
        description=evidence_data.description,
        content=evidence_data.content,
        source=evidence_data.source,
        collected_at=evidence_data.collected_at,
        collected_by=evidence_data.collected_by,
        is_auto_collected=evidence_data.is_auto_collected,
        integrity_hash=evidence_data.integrity_hash,
        tenant_id=evidence_data.tenant_id,
    )
    db.add(evidence)
    await db.flush()
    logger.info(
        "取证证据已创建",
        evidence_id=evidence.id,
        evidence_type=evidence.evidence_type,
        incident_id=evidence.incident_id,
    )
    return evidence


async def get_evidence(db: AsyncSession, evidence_id: int) -> ForensicEvidence | None:
    """根据 ID 获取取证证据。"""
    stmt = select(ForensicEvidence).where(ForensicEvidence.id == evidence_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_evidences(
    db: AsyncSession,
    query_params: ForensicEvidenceQueryParams,
    skip: int = 0,
    limit: int = 50,
) -> list[ForensicEvidence]:
    """查询取证证据列表。"""
    stmt = select(ForensicEvidence)

    if query_params.incident_id is not None:
        stmt = stmt.where(ForensicEvidence.incident_id == query_params.incident_id)
    if query_params.alert_id is not None:
        stmt = stmt.where(ForensicEvidence.alert_id == query_params.alert_id)
    if query_params.evidence_type:
        stmt = stmt.where(ForensicEvidence.evidence_type == query_params.evidence_type)
    if query_params.start_time:
        stmt = stmt.where(ForensicEvidence.collected_at >= query_params.start_time)
    if query_params.end_time:
        stmt = stmt.where(ForensicEvidence.collected_at <= query_params.end_time)

    stmt = stmt.order_by(ForensicEvidence.collected_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_evidences(db: AsyncSession, query_params: ForensicEvidenceQueryParams) -> int:
    """统计取证证据数量。"""
    stmt = select(func.count(ForensicEvidence.id))

    if query_params.incident_id is not None:
        stmt = stmt.where(ForensicEvidence.incident_id == query_params.incident_id)
    if query_params.alert_id is not None:
        stmt = stmt.where(ForensicEvidence.alert_id == query_params.alert_id)
    if query_params.evidence_type:
        stmt = stmt.where(ForensicEvidence.evidence_type == query_params.evidence_type)
    if query_params.start_time:
        stmt = stmt.where(ForensicEvidence.collected_at >= query_params.start_time)
    if query_params.end_time:
        stmt = stmt.where(ForensicEvidence.collected_at <= query_params.end_time)

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_evidences_by_incident(db: AsyncSession, incident_id: int) -> list[ForensicEvidence]:
    """获取事件关联的全部取证证据。"""
    stmt = (
        select(ForensicEvidence)
        .where(ForensicEvidence.incident_id == incident_id)
        .order_by(ForensicEvidence.collected_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# 各类证据采集器
# ──────────────────────────────────────────────


async def _collect_roa_vrp_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    asns: list[int],
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集 ROA/VRP 授权证据。"""
    count = 0
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

        content = {
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
                    "origin_as": getattr(r, "origin_as", None),
                    "max_length": getattr(r, "max_length", None),
                }
                for r in roas
            ],
        }

        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="roa_vrp",
                title=f"ROA/VRP 授权证据 - {prefix}",
                description=f"前缀 {prefix} 的 ROA/VRP 授权快照",
                content=content,
                source="local_rpki_cache",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    return count


async def _collect_bgp_sample_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集 BGP 公告与撤路样本证据。"""
    count = 0
    for prefix in prefixes:
        # 查询公告样本
        ann_stmt = (
            select(BGPAnnouncement)
            .where(BGPAnnouncement.prefix == prefix)
            .where(BGPAnnouncement.timestamp >= window_start)
            .where(BGPAnnouncement.timestamp <= window_end)
            .order_by(BGPAnnouncement.timestamp.desc())
            .limit(50)
        )
        ann_result = await db.execute(ann_stmt)
        announcements = list(ann_result.scalars().all())

        # 查询撤路样本
        wd_stmt = (
            select(BGPWithdraw)
            .where(BGPWithdraw.prefix == prefix)
            .where(BGPWithdraw.timestamp >= window_start)
            .where(BGPWithdraw.timestamp <= window_end)
            .order_by(BGPWithdraw.timestamp.desc())
            .limit(50)
        )
        wd_result = await db.execute(wd_stmt)
        withdraws = list(wd_result.scalars().all())

        if not announcements and not withdraws:
            continue

        content = {
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

        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="bgp_sample",
                title=f"BGP 样本证据 - {prefix}",
                description=(f"前缀 {prefix} 在事件时间窗口内的 BGP 公告与撤路样本"),
                content=content,
                source="local_bgp_cache",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    return count


async def _collect_as_path_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集 AS_PATH 路径证据。"""
    count = 0
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

        paths = []
        unique_paths = set()
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

        content = {
            "prefix": prefix,
            "unique_path_count": len(paths),
            "paths": paths[:50],
        }

        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="as_path",
                title=f"AS_PATH 路径证据 - {prefix}",
                description=f"前缀 {prefix} 的 AS_PATH 路径多样性快照",
                content=content,
                source="local_bgp_cache",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    return count


async def _collect_propagation_scope_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集传播范围证据（观察点分布）。"""
    count = 0
    for prefix in prefixes:
        # 统计观察到该前缀的观察点数量
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

        if not rows:
            continue

        observation_points = [
            {
                "observation_point_id": row[0],
                "announcement_count": int(row[1]),
            }
            for row in rows
        ]

        content = {
            "prefix": prefix,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "observation_point_count": len(observation_points),
            "observation_points": observation_points,
        }

        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="propagation_scope",
                title=f"传播范围证据 - {prefix}",
                description=(f"前缀 {prefix} 在 {len(observation_points)} 个观察点被观察到"),
                content=content,
                source="local_bgp_cache",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    return count


async def _collect_observation_point_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    window_start: datetime,
    window_end: datetime,
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集观察点信息证据。"""
    # 查询所有观察点
    op_stmt = select(ObservationPoint).where(ObservationPoint.status == "active")
    op_result = await db.execute(op_stmt)
    observation_points = list(op_result.scalars().all())

    if not observation_points:
        return 0

    content = {
        "observation_points": [
            {
                "id": op.id,
                "name": op.name,
                "location": op.location,
                "collector_id": op.collector_id,
                "ip_version": op.ip_version,
            }
            for op in observation_points
        ],
        "total_count": len(observation_points),
    }

    await create_evidence(
        db,
        ForensicEvidenceCreate(
            incident_id=incident_id,
            alert_id=alert_id,
            evidence_type="observation_point",
            title="观察点信息证据",
            description=f"当前活跃观察点共 {len(observation_points)} 个",
            content=content,
            source="local_collector",
            collected_at=collected_at,
            collected_by=collected_by,
            is_auto_collected=True,
            integrity_hash=_compute_hash(content),
        ),
    )
    return 1


async def _collect_asset_relation_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    asns: list[int],
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集资产关系证据（前缀、客户、业务服务、ASN）。"""
    count = 0

    # 前缀资产关系
    prefix_assets = []
    for prefix in prefixes:
        stmt = select(Prefix).where(Prefix.prefix == prefix)
        result = await db.execute(stmt)
        prefix_obj = result.scalar_one_or_none()
        if prefix_obj is None:
            continue

        asset_info: dict[str, Any] = {
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

        prefix_assets.append(asset_info)

    if prefix_assets:
        content = {
            "prefixes": prefix_assets,
            "prefix_count": len(prefix_assets),
        }
        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="asset_relation",
                title="资产关系证据",
                description=f"关联前缀资产 {len(prefix_assets)} 个",
                content=content,
                source="asset_registry",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    # ASN 资产关系
    asn_assets = []
    for asn in asns:
        stmt = select(ASN).where(ASN.asn == asn)
        result = await db.execute(stmt)
        asn_obj = result.scalar_one_or_none()
        if asn_obj is None:
            continue
        asn_assets.append(
            {
                "asn": asn_obj.asn,
                "name": asn_obj.name,
                "risk_profile": asn_obj.risk_profile,
                "country": getattr(asn_obj, "country", None),
            }
        )

    if asn_assets:
        content = {
            "asns": asn_assets,
            "asn_count": len(asn_assets),
        }
        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="asset_relation",
                title="ASN 资产关系证据",
                description=f"关联 ASN 资产 {len(asn_assets)} 个",
                content=content,
                source="asset_registry",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    return count


async def _collect_change_record_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    asns: list[int],
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集变更记录证据（占位实现）。

    TODO: 接入变更管理系统后，查询事件时间窗口内的 ROA 变更、
    路由策略变更、维护窗口等变更记录。
    """
    content = {
        "prefixes": prefixes,
        "asns": asns,
        "note": "变更记录采集为占位实现，待接入变更管理系统",
        "change_records": [],
    }

    await create_evidence(
        db,
        ForensicEvidenceCreate(
            incident_id=incident_id,
            alert_id=alert_id,
            evidence_type="change_record",
            title="变更记录证据",
            description="事件时间窗口内的变更记录（占位）",
            content=content,
            source="change_management_system",
            collected_at=collected_at,
            collected_by=collected_by,
            is_auto_collected=True,
            integrity_hash=_compute_hash(content),
        ),
    )
    return 1


async def _collect_historical_baseline_evidence(
    db: AsyncSession,
    incident_id: int | None,
    alert_id: int | None,
    prefixes: list[str],
    asns: list[int],
    collected_at: datetime,
    collected_by: int | None,
) -> int:
    """采集历史基线证据（30 天内的 origin AS 历史）。"""
    count = 0
    since = collected_at - timedelta(days=30)

    for prefix in prefixes:
        # 查询历史 origin AS
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

        content = {
            "prefix": prefix,
            "baseline_window_days": 30,
            "historical_origin_asns": historical_origins,
            "unique_origin_count": len(historical_origins),
            "is_moas": len(historical_origins) >= 2,
        }

        await create_evidence(
            db,
            ForensicEvidenceCreate(
                incident_id=incident_id,
                alert_id=alert_id,
                evidence_type="historical_baseline",
                title=f"历史基线证据 - {prefix}",
                description=(f"前缀 {prefix} 近 30 天的 origin AS 基线"),
                content=content,
                source="local_bgp_cache",
                collected_at=collected_at,
                collected_by=collected_by,
                is_auto_collected=True,
                integrity_hash=_compute_hash(content),
            ),
        )
        count += 1

    return count


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _get_incident(db: AsyncSession, incident_id: int) -> Incident | None:
    """获取事件。"""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_alert(db: AsyncSession, alert_id: int) -> Alert | None:
    """获取告警。"""
    stmt = select(Alert).where(Alert.id == alert_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _compute_hash(content: Any) -> str:
    """计算证据内容的完整性哈希（SHA-256）。

    用于防篡改校验，确保证据内容未被修改。
    """
    try:
        content_str = json.dumps(content, sort_keys=True, default=str)
    except (TypeError, ValueError):
        content_str = str(content)
    return hashlib.sha256(content_str.encode("utf-8")).hexdigest()


__all__ = [
    "collect_forensic_evidence",
    "count_evidences",
    "create_evidence",
    "get_evidence",
    "get_evidences",
    "get_evidences_by_incident",
]
