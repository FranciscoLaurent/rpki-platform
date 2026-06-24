"""驾驶舱数据聚合服务。

提供总览驾驶舱、前缀详情、ASN 详情与事件时间线的数据聚合能力。
所有方法均使用 SQLAlchemy 2.0 异步风格，从多个模型聚合数据。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement, BGPDataSource
from app.models.detection import Alert, Incident
from app.models.prefix import Prefix
from app.models.rpki import ROA, VRP, RPKICache
from app.schemas.dashboard import (
    ASNAlertItem,
    ASNAssetInfo,
    ASNDetail,
    ASNPrefixItem,
    ASNStats,
    AuthorizedOrigin,
    BGPSourceStatus,
    CurrentAnnouncement,
    DashboardOverview,
    IncidentBasicInfo,
    IncidentStats,
    IncidentTimeline,
    IncidentTimelineItem,
    MatchedVRP,
    PrefixAlertItem,
    PrefixAssetInfo,
    PrefixDetail,
    PrefixStats,
    RiskTrendPoint,
    ROACoverage,
    RPKICacheStatus,
    ValidationDistribution,
)
from app.services.vrp_service import _get_covering_prefixes

logger = get_logger("app.dashboard_service")


# ──────────────────────────────────────────────
# 总览驾驶舱
# ──────────────────────────────────────────────


async def get_dashboard_overview(db: AsyncSession) -> DashboardOverview:
    """获取总览驾驶舱数据。

    聚合以下信息：
    - 企业 IP/ASN 数量统计
    - ROA 覆盖率
    - Valid/Invalid/NotFound 分布
    - P0/P1 事件数量
    - RPKI cache 状态
    - BGP 数据源状态
    - 风险趋势（最近 7 天）

    Args:
        db: 异步数据库会话

    Returns:
        驾驶舱总览数据
    """
    prefix_stats = await _get_prefix_stats(db)
    asn_stats = await _get_asn_stats(db)
    roa_coverage = await _get_roa_coverage(db)
    validation_distribution = await _get_validation_distribution(db)
    incident_stats = await _get_incident_stats(db)
    rpki_cache_status = await _get_rpki_cache_status(db)
    bgp_source_status = await _get_bgp_source_status(db)
    risk_trend = await _get_risk_trend(db)

    return DashboardOverview(
        prefix_stats=prefix_stats,
        asn_stats=asn_stats,
        roa_coverage=roa_coverage,
        validation_distribution=validation_distribution,
        incident_stats=incident_stats,
        rpki_cache_status=rpki_cache_status,
        bgp_source_status=bgp_source_status,
        risk_trend=risk_trend,
    )


async def _get_prefix_stats(db: AsyncSession) -> PrefixStats:
    """获取前缀统计信息。"""
    total_result = await db.execute(select(func.count(Prefix.id)))
    total = int(total_result.scalar_one() or 0)

    active_result = await db.execute(select(func.count(Prefix.id)).where(Prefix.status == "active"))
    active = int(active_result.scalar_one() or 0)

    # 按重要度分组
    importance_result = await db.execute(
        select(Prefix.importance, func.count(Prefix.id)).group_by(Prefix.importance)
    )
    by_importance = {row[0]: int(row[1]) for row in importance_result}

    # 按协议族分组
    family_result = await db.execute(
        select(Prefix.prefix_family, func.count(Prefix.id)).group_by(Prefix.prefix_family)
    )
    by_family = {("ipv4" if row[0] == 4 else "ipv6"): int(row[1]) for row in family_result}

    return PrefixStats(
        total=total,
        active=active,
        by_importance=by_importance,
        by_family=by_family,
    )


async def _get_asn_stats(db: AsyncSession) -> ASNStats:
    """获取 ASN 统计信息。"""
    total_result = await db.execute(select(func.count(ASN.id)))
    total = int(total_result.scalar_one() or 0)

    type_result = await db.execute(select(ASN.asn_type, func.count(ASN.id)).group_by(ASN.asn_type))
    by_type = {row[0]: int(row[1]) for row in type_result}

    return ASNStats(total=total, by_type=by_type)


async def _get_roa_coverage(db: AsyncSession) -> ROACoverage:
    """获取 ROA 覆盖率。

    复用 ``roa_validation_service.get_roa_coverage_stats`` 的精确匹配逻辑，
    确保 Dashboard 与 ROA 管理页面的覆盖率数据一致。
    """
    from app.services.roa_validation_service import get_roa_coverage_stats

    stats = await get_roa_coverage_stats(db)
    return ROACoverage(
        total_prefixes=stats.total_prefixes,
        prefixes_with_roa=stats.covered_prefixes,
        coverage_rate=round(stats.coverage_rate, 4),
        missing_count=stats.total_prefixes - stats.covered_prefixes,
    )


async def _get_validation_distribution(db: AsyncSession) -> ValidationDistribution:
    """获取 BGP 公告 RPKI 验证状态分布。"""
    result = await db.execute(
        select(
            BGPAnnouncement.rpki_validation_status,
            func.count(BGPAnnouncement.id),
        )
        .where(BGPAnnouncement.rpki_validation_status.isnot(None))
        .group_by(BGPAnnouncement.rpki_validation_status)
    )
    distribution = {row[0]: int(row[1]) for row in result}

    valid = distribution.get("valid", 0)
    invalid = distribution.get("invalid", 0)
    not_found = distribution.get("not_found", 0)
    total = valid + invalid + not_found

    return ValidationDistribution(
        valid=valid,
        invalid=invalid,
        not_found=not_found,
        total=total,
    )


async def _get_incident_stats(db: AsyncSession) -> IncidentStats:
    """获取事件统计信息（仅统计未关闭事件）。"""
    open_statuses = ("open", "investigating", "mitigating")
    result = await db.execute(
        select(Incident.severity, func.count(Incident.id))
        .where(Incident.status.in_(open_statuses))
        .group_by(Incident.severity)
    )
    severity_count = {row[0]: int(row[1]) for row in result}

    total_open_result = await db.execute(
        select(func.count(Incident.id)).where(Incident.status.in_(open_statuses))
    )
    total_open = int(total_open_result.scalar_one() or 0)

    return IncidentStats(
        p0=severity_count.get("P0", 0),
        p1=severity_count.get("P1", 0),
        p2=severity_count.get("P2", 0),
        p3=severity_count.get("P3", 0),
        p4=severity_count.get("P4", 0),
        total_open=total_open,
    )


async def _get_rpki_cache_status(db: AsyncSession) -> RPKICacheStatus:
    """获取 RPKI 缓存状态。"""
    result = await db.execute(select(RPKICache).order_by(RPKICache.last_updated.desc()))
    caches = list(result.scalars().all())

    if not caches:
        return RPKICacheStatus(
            cache_count=0,
            last_update=None,
            vrp_count=0,
            status="unknown",
        )

    cache_count = len(caches)
    vrp_count = sum(c.vrp_count for c in caches)
    last_update = max((c.last_updated for c in caches if c.last_updated), default=None)

    # 整体状态：所有缓存健康则为 healthy，存在 stale 则为 stale
    if all(c.status == "healthy" for c in caches):
        status = "healthy"
    elif any(c.status == "stale" for c in caches):
        status = "stale"
    else:
        status = "unknown"

    return RPKICacheStatus(
        cache_count=cache_count,
        last_update=last_update,
        vrp_count=vrp_count,
        status=status,
    )


async def _get_bgp_source_status(db: AsyncSession) -> BGPSourceStatus:
    """获取 BGP 数据源状态。"""
    total_result = await db.execute(select(func.count(BGPDataSource.id)))
    total = int(total_result.scalar_one() or 0)

    active_result = await db.execute(
        select(func.count(BGPDataSource.id)).where(BGPDataSource.status == "active")
    )
    active = int(active_result.scalar_one() or 0)

    error_result = await db.execute(
        select(func.count(BGPDataSource.id)).where(BGPDataSource.status == "error")
    )
    error = int(error_result.scalar_one() or 0)

    type_result = await db.execute(
        select(BGPDataSource.source_type, func.count(BGPDataSource.id)).group_by(
            BGPDataSource.source_type
        )
    )
    by_type = {row[0]: int(row[1]) for row in type_result}

    return BGPSourceStatus(
        active=active,
        error=error,
        total=total,
        by_type=by_type,
    )


async def _get_risk_trend(db: AsyncSession) -> list[RiskTrendPoint]:
    """获取最近 7 天的风险趋势。"""
    now = datetime.now(UTC)
    start_date = (now - timedelta(days=6)).date()

    # 按日期分组统计告警（使用 SQLite 兼容的 DATE() 函数）
    alert_result = await db.execute(
        select(
            func.date(Alert.created_at).label("day"),
            func.count(Alert.id),
        )
        .where(Alert.created_at >= datetime.combine(start_date, datetime.min.time()))
        .group_by("day")
        .order_by("day")
    )
    alert_map: dict[str, int] = {}
    for row in alert_result:
        day_str = str(row[0]) if row[0] is not None else ""
        alert_map[day_str] = int(row[1])

    # 按日期分组统计事件
    incident_result = await db.execute(
        select(
            func.date(Incident.created_at).label("day"),
            func.count(Incident.id),
        )
        .where(Incident.created_at >= datetime.combine(start_date, datetime.min.time()))
        .group_by("day")
        .order_by("day")
    )
    incident_map: dict[str, int] = {}
    for row in incident_result:
        day_str = str(row[0]) if row[0] is not None else ""
        incident_map[day_str] = int(row[1])

    # 构建连续 7 天的趋势数据
    trend: list[RiskTrendPoint] = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_str = day.isoformat()
        trend.append(
            RiskTrendPoint(
                date=day_str,
                alert_count=alert_map.get(day_str, 0),
                incident_count=incident_map.get(day_str, 0),
            )
        )

    return trend


# ──────────────────────────────────────────────
# 前缀详情
# ──────────────────────────────────────────────


async def get_prefix_detail(db: AsyncSession, prefix_id: int) -> PrefixDetail | None:
    """获取前缀详情。

    聚合以下信息：
    - 资产属性（Prefix 基本信息）
    - 合法 origin（从 ROA 查询授权的 origin AS）
    - 当前公告（从 BGPAnnouncement 查询该前缀的公告）
    - AS_PATH（从公告中提取）
    - ROA/VRP 命中（查询匹配的 ROA 和 VRP）
    - IRR 信息（占位，TODO）
    - 历史状态（占位，从 ClickHouse 查询历史）
    - 告警（从 Alert 表查询该前缀的告警）
    - 业务影响（从 Prefix 的 business_service 字段）
    - 操作建议（基于以上信息生成建议）

    Args:
        db: 异步数据库会话
        prefix_id: 前缀 ID

    Returns:
        前缀详情，前缀不存在返回 None
    """
    # 查询前缀基本信息
    prefix_result = await db.execute(select(Prefix).where(Prefix.id == prefix_id))
    prefix = prefix_result.scalar_one_or_none()
    if prefix is None:
        return None

    asset = PrefixAssetInfo.model_validate(prefix)

    # 查询匹配的 ROA（覆盖该前缀的所有 ROA）
    covering_prefixes = _get_covering_prefixes(prefix.prefix)
    matched_roas: list[AuthorizedOrigin] = []
    if covering_prefixes:
        roa_result = await db.execute(
            select(ROA).where(ROA.prefix.in_(covering_prefixes)).limit(100)
        )
        for roa in roa_result.scalars().all():
            matched_roas.append(
                AuthorizedOrigin(
                    roa_id=roa.id,
                    origin_as=roa.origin_as,
                    prefix=roa.prefix,
                    max_length=roa.max_length,
                    tal_id=roa.tal_id,
                    status=roa.status,
                    not_before=roa.not_before,
                    not_after=roa.not_after,
                )
            )

    # 查询匹配的 VRP
    matched_vrps: list[MatchedVRP] = []
    if covering_prefixes:
        vrp_result = await db.execute(
            select(VRP).where(VRP.prefix.in_(covering_prefixes)).limit(100)
        )
        for vrp in vrp_result.scalars().all():
            matched_vrps.append(MatchedVRP.model_validate(vrp))

    # 查询当前公告
    announcement_result = await db.execute(
        select(BGPAnnouncement)
        .where(BGPAnnouncement.prefix == prefix.prefix)
        .order_by(BGPAnnouncement.timestamp.desc())
        .limit(100)
    )
    announcements = list(announcement_result.scalars().all())
    current_announcements = [CurrentAnnouncement.model_validate(a) for a in announcements]

    # 提取去重后的 AS_PATH
    as_paths: list[list[int]] = []
    seen_paths: set[tuple[int, ...]] = set()
    for ann in announcements:
        if ann.as_path:
            path_tuple = tuple(ann.as_path)
            if path_tuple not in seen_paths:
                seen_paths.add(path_tuple)
                as_paths.append(list(ann.as_path))

    # 查询告警
    alert_result = await db.execute(
        select(Alert)
        .where(Alert.prefix == prefix.prefix)
        .order_by(Alert.created_at.desc())
        .limit(50)
    )
    alerts = [PrefixAlertItem.model_validate(a) for a in alert_result.scalars().all()]

    # 生成操作建议
    recommendations = _generate_prefix_recommendations(
        prefix=prefix,
        matched_roas=matched_roas,
        matched_vrps=matched_vrps,
        announcements=announcements,
        alerts=alerts,
    )

    return PrefixDetail(
        asset=asset,
        authorized_origins=matched_roas,
        current_announcements=current_announcements,
        as_paths=as_paths,
        matched_roas=matched_roas,
        matched_vrps=matched_vrps,
        irr_info=None,  # TODO: 对接 IRR 查询
        history=[],  # TODO: 从 ClickHouse 查询历史
        alerts=alerts,
        business_impact=prefix.business_service,
        recommendations=recommendations,
    )


def _generate_prefix_recommendations(
    prefix: Prefix,
    matched_roas: list[AuthorizedOrigin],
    matched_vrps: list[MatchedVRP],
    announcements: list[BGPAnnouncement],
    alerts: list[PrefixAlertItem],
) -> list[str]:
    """基于前缀详情生成操作建议。"""
    recommendations: list[str] = []

    # ROA 覆盖检查
    if not matched_roas:
        recommendations.append(
            f"前缀 {prefix.prefix} 未配置 ROA，建议尽快创建 ROA 以启用 RPKI 验证保护。"
        )

    # RPKI 验证状态检查
    invalid_announcements = [a for a in announcements if a.rpki_validation_status == "invalid"]
    if invalid_announcements:
        recommendations.append(
            f"检测到 {len(invalid_announcements)} 条 RPKI Invalid 公告，"
            "请检查 origin AS 是否被授权或前缀长度是否超过 maxLength。"
        )

    not_found_announcements = [a for a in announcements if a.rpki_validation_status == "not_found"]
    if not_found_announcements and matched_roas:
        recommendations.append(
            f"检测到 {len(not_found_announcements)} 条 NotFound 公告，"
            "可能存在未授权的 origin AS 公告该前缀。"
        )

    # 告警检查
    open_alerts = [a for a in alerts if a.status in ("new", "confirmed", "assigned")]
    if open_alerts:
        p0_p1 = [a for a in open_alerts if a.severity in ("P0", "P1")]
        if p0_p1:
            recommendations.append(f"存在 {len(p0_p1)} 条 P0/P1 高危告警，建议立即处置。")
        else:
            recommendations.append(f"存在 {len(open_alerts)} 条未关闭告警，建议尽快确认与处置。")

    # 重要度建议
    if prefix.importance == "critical" and not matched_roas:
        recommendations.append("该前缀为关键资产，强烈建议立即配置 ROA 并启用 BGP 公告验证。")

    # 业务影响建议
    if prefix.business_service and invalid_announcements:
        recommendations.append(
            f"该前缀关联业务 {prefix.business_service}，"
            "Invalid 公告可能影响业务可用性，建议通知业务方并启动应急响应。"
        )

    if not recommendations:
        recommendations.append("当前前缀状态正常，无紧急处置建议。")

    return recommendations


# ──────────────────────────────────────────────
# ASN 详情
# ──────────────────────────────────────────────


async def get_asn_detail(db: AsyncSession, asn_id: int) -> ASNDetail | None:
    """获取 ASN 详情。

    聚合以下信息：
    - ASN 基本信息
    - 关联前缀（该 ASN 作为 origin 的前缀）
    - 上游/下游/对等关系（占位，从 BGP AS_PATH 分析）
    - 历史路径（占位）
    - 异常记录（从 Alert 表查询该 ASN 的告警）
    - 风险画像（从 ASN 的 risk_profile 字段）

    Args:
        db: 异步数据库会话
        asn_id: ASN ID

    Returns:
        ASN 详情，ASN 不存在返回 None
    """
    # 查询 ASN 基本信息
    asn_result = await db.execute(select(ASN).where(ASN.id == asn_id))
    asn = asn_result.scalar_one_or_none()
    if asn is None:
        return None

    asset = ASNAssetInfo.model_validate(asn)

    # 查询该 ASN 作为 origin 的前缀
    # 通过 BGP 公告表反查前缀，再关联 Prefix 表
    announcement_result = await db.execute(
        select(BGPAnnouncement.prefix).where(BGPAnnouncement.origin_as == asn.asn).distinct()
    )
    origin_prefixes = {row[0] for row in announcement_result}

    related_prefixes: list[ASNPrefixItem] = []
    if origin_prefixes:
        prefix_result = await db.execute(
            select(Prefix).where(Prefix.prefix.in_(origin_prefixes)).limit(200)
        )
        related_prefixes = [ASNPrefixItem.model_validate(p) for p in prefix_result.scalars().all()]

    # 查询告警
    alert_result = await db.execute(
        select(Alert).where(Alert.origin_as == asn.asn).order_by(Alert.created_at.desc()).limit(50)
    )
    alerts = [ASNAlertItem.model_validate(a) for a in alert_result.scalars().all()]

    # 占位：从 BGP AS_PATH 分析上下游关系
    # TODO: 实现完整的 AS 关系分析
    upstream: list[int] = []
    downstream: list[int] = []
    peers: list[int] = []

    return ASNDetail(
        asset=asset,
        related_prefixes=related_prefixes,
        upstream=upstream,
        downstream=downstream,
        peers=peers,
        history_paths=[],  # TODO: 从 ClickHouse 查询历史路径
        alerts=alerts,
        risk_profile=asn.risk_profile,
    )


# ──────────────────────────────────────────────
# 事件时间线
# ──────────────────────────────────────────────


async def get_incident_timeline(db: AsyncSession, incident_id: int) -> IncidentTimeline | None:
    """获取事件时间线。

    构建以下时间线事件：
    - 首次出现时间
    - 传播变化事件
    - 告警生成事件
    - 人工确认事件
    - 处置事件
    - 恢复事件
    - 关闭事件

    从 Incident 的 timeline 字段和关联 Alert 的时间戳构建。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID

    Returns:
        事件时间线，事件不存在返回 None
    """
    incident_result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = incident_result.scalar_one_or_none()
    if incident is None:
        return None

    basic_info = IncidentBasicInfo.model_validate(incident)

    # 构建时间线
    timeline_items: list[IncidentTimelineItem] = []

    # 1. 首次出现时间
    if incident.first_seen_at:
        timeline_items.append(
            IncidentTimelineItem(
                timestamp=incident.first_seen_at,
                event_type="first_seen",
                description="事件首次出现",
                operator=None,
            )
        )

    # 2. 从 Incident.timeline 字段加载已有事件
    if incident.timeline:
        for item in incident.timeline:
            if not isinstance(item, dict):
                continue
            ts = item.get("timestamp")
            if ts is None:
                continue
            try:
                timestamp = _parse_datetime(ts)
            except (ValueError, TypeError):
                continue
            timeline_items.append(
                IncidentTimelineItem(
                    timestamp=timestamp,
                    event_type=str(item.get("event_type", "unknown")),
                    description=str(item.get("description", "")),
                    operator=item.get("operator"),
                )
            )

    # 3. 查询关联告警，按时间戳生成告警事件
    if incident.alert_ids:
        alert_result = await db.execute(
            select(Alert).where(Alert.id.in_(incident.alert_ids)).order_by(Alert.created_at.asc())
        )
        related_alerts: list[dict[str, Any]] = []
        for alert in alert_result.scalars().all():
            related_alerts.append(
                {
                    "id": alert.id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "prefix": alert.prefix,
                    "origin_as": alert.origin_as,
                    "status": alert.status,
                    "risk_score": alert.risk_score,
                    "first_seen_at": (
                        alert.first_seen_at.isoformat() if alert.first_seen_at else None
                    ),
                    "last_seen_at": (
                        alert.last_seen_at.isoformat() if alert.last_seen_at else None
                    ),
                    "created_at": alert.created_at.isoformat(),
                }
            )
            timeline_items.append(
                IncidentTimelineItem(
                    timestamp=alert.created_at,
                    event_type="alert",
                    description=f"告警生成：{alert.title}（{alert.severity}）",
                    operator=None,
                )
            )
    else:
        related_alerts = []

    # 4. 恢复事件
    if incident.resolved_at:
        timeline_items.append(
            IncidentTimelineItem(
                timestamp=incident.resolved_at,
                event_type="resolved",
                description="事件已恢复",
                operator=None,
            )
        )

    # 5. 关闭事件
    if incident.closed_at:
        timeline_items.append(
            IncidentTimelineItem(
                timestamp=incident.closed_at,
                event_type="closed",
                description=f"事件已关闭：{incident.resolution or '无处置结论'}",
                operator=None,
            )
        )

    # 按时间排序
    timeline_items.sort(key=lambda x: x.timestamp)

    # 构建影响范围摘要
    impact_scope: dict[str, Any] = {
        "affected_prefixes": incident.affected_prefixes or [],
        "affected_asns": incident.affected_asns or [],
        "alert_count": len(related_alerts),
    }

    # 生成处置建议
    recommendations = _generate_incident_recommendations(incident, related_alerts)

    return IncidentTimeline(
        incident=basic_info,
        timeline=timeline_items,
        related_alerts=related_alerts,
        impact_scope=impact_scope,
        recommendations=recommendations,
        root_cause_analysis=incident.root_cause,
    )


def _parse_datetime(value: Any) -> datetime:
    """解析时间字符串或 datetime 对象为 datetime。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # 处理 ISO 格式字符串
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"无法解析时间值: {value}")


def _generate_incident_recommendations(
    incident: Incident, related_alerts: list[dict[str, Any]]
) -> list[str]:
    """基于事件信息生成处置建议。"""
    recommendations: list[str] = []

    # 严重等级建议
    if incident.severity in ("P0", "P1"):
        recommendations.append(
            f"事件等级为 {incident.severity}，建议立即启动应急响应流程，"
            "通知 NOC、安全团队与业务方。"
        )
    elif incident.severity == "P2":
        recommendations.append("事件等级为 P2，建议在 1 小时内确认并分派处置人员。")

    # 状态建议
    if incident.status == "open":
        recommendations.append("事件尚未分派，建议立即分派给相关责任人。")
    elif incident.status == "investigating":
        recommendations.append("事件正在调查中，建议尽快确定根因并制定处置方案。")
    elif incident.status == "mitigating":
        recommendations.append("事件正在处置中，建议持续监控传播范围与业务影响。")

    # 告警建议
    if related_alerts:
        invalid_alerts = [a for a in related_alerts if a.get("alert_type") == "rpki_invalid"]
        if invalid_alerts:
            recommendations.append(
                f"检测到 {len(invalid_alerts)} 条 RPKI Invalid 告警，"
                "建议联系相关 AS 的 NOC 并考虑在边界路由器过滤 Invalid 路由。"
            )

        hijack_alerts = [
            a for a in related_alerts if a.get("alert_type") in ("hijack", "subprefix_hijack")
        ]
        if hijack_alerts:
            recommendations.append(
                f"检测到 {len(hijack_alerts)} 条前缀劫持告警，"
                "建议立即核实公告真实性，必要时通过 RPKI 与 IRR 双重验证。"
            )

    # 影响范围建议
    affected_prefixes = incident.affected_prefixes or []
    if affected_prefixes:
        recommendations.append(
            f"受影响前缀 {len(affected_prefixes)} 个，建议评估业务影响范围并通知相关业务方。"
        )

    if not recommendations:
        recommendations.append("事件状态正常，建议持续监控。")

    return recommendations


__all__ = [
    "get_asn_detail",
    "get_dashboard_overview",
    "get_incident_timeline",
    "get_prefix_detail",
]
