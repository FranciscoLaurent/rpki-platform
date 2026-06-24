"""ROA 验证服务。

提供 ROA 与 BGP 公告的一致性验证、ROA 覆盖率统计与 ROA 健康度摘要。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.prefix import Prefix
from app.models.rpki import ROA, VRP
from app.schemas.roa import (
    ROACoverageByImportance,
    ROACoverageByStatus,
    ROACoverageStats,
    ROAHealthSummary,
)
from app.services import roa_service, vrp_service

logger = get_logger("app.roa_validation_service")


# ──────────────────────────────────────────────
# ROA 与 BGP 一致性验证
# ──────────────────────────────────────────────


async def validate_roa_against_bgp(
    db: AsyncSession, roa_id: int
) -> dict[str, Any]:
    """验证 ROA 与 BGP 公告的一致性。

    检查 ROA 是否与实际 BGP 公告匹配：
    1. ROA 授权的前缀是否有对应的 BGP 公告
    2. ROA 授权的 origin AS 是否与实际公告一致
    3. ROA 的 maxLength 是否合理（覆盖实际公告但不至于过宽）

    Args:
        db: 异步数据库会话
        roa_id: ROA ID

    Returns:
        一致性验证结果字典，包含：
        - roa_id: ROA ID
        - is_consistent: 是否一致
        - has_matching_announcement: 是否有匹配的 BGP 公告
        - origin_as_matched: origin AS 是否匹配
        - max_length_appropriate: maxLength 是否合理
        - issues: 发现的问题列表
        - matched_announcements: 匹配的公告列表
    """
    roa = await roa_service.get_roa_detail(db, roa_id)
    if roa is None:
        return {
            "roa_id": roa_id,
            "is_consistent": False,
            "error": f"ROA ID {roa_id} 不存在",
        }

    # 获取关联的 BGP 公告
    related_announcements = await roa_service.get_related_bgp_announcements(
        db, roa
    )

    issues: list[str] = []
    has_matching = False
    origin_matched = False
    max_length_appropriate = True

    if not related_announcements:
        issues.append("ROA 授权的前缀无对应的 BGP 公告（孤儿 ROA）")
    else:
        for ann in related_announcements:
            # 检查 origin AS 匹配
            if ann.origin_as == roa.origin_as:
                origin_matched = True
                has_matching = True
            else:
                issues.append(
                    f"公告 {ann.prefix} 的 origin AS {ann.origin_as} "
                    f"与 ROA 授权的 {roa.origin_as} 不匹配"
                )

            # 检查 maxLength 是否过宽
            effective_max_length = roa.max_length or roa.prefix_length
            if (
                effective_max_length > ann.prefix_length + 8
                and ann.origin_as == roa.origin_as
            ):
                max_length_appropriate = False
                issues.append(
                    f"maxLength={effective_max_length} 远大于实际公告长度 "
                    f"{ann.prefix_length}，存在劫持风险"
                )

    if not origin_matched and related_announcements:
        issues.append("无任何公告的 origin AS 与 ROA 授权一致")

    is_consistent = (
        has_matching and origin_matched and max_length_appropriate
    )

    return {
        "roa_id": roa_id,
        "is_consistent": is_consistent,
        "has_matching_announcement": has_matching,
        "origin_as_matched": origin_matched,
        "max_length_appropriate": max_length_appropriate,
        "issues": issues,
        "matched_announcement_count": len(related_announcements),
    }


# ──────────────────────────────────────────────
# ROA 覆盖率统计
# ──────────────────────────────────────────────


async def get_roa_coverage_stats(db: AsyncSession) -> ROACoverageStats:
    """获取 ROA 覆盖率统计。

    统计内容：
    - 总前缀数、有 ROA 的前缀数、覆盖率
    - 按重要性分级统计
    - 按状态（Valid/Invalid/NotFound）统计

    Args:
        db: 异步数据库会话

    Returns:
        ROA 覆盖率统计
    """
    # 查询所有已登记前缀
    prefix_stmt = select(Prefix.prefix, Prefix.importance)
    prefix_result = await db.execute(prefix_stmt)
    all_prefixes = list(prefix_result.all())

    # 查询所有 ROA 的前缀集合
    roa_stmt = select(ROA.prefix).where(ROA.status == "valid")
    roa_result = await db.execute(roa_stmt)
    roa_prefixes: set[str] = {row.prefix for row in roa_result}

    # 按重要度分组统计
    importance_groups: dict[str, dict[str, int]] = {}
    for row in all_prefixes:
        importance = row.importance or "normal"
        if importance not in importance_groups:
            importance_groups[importance] = {"total": 0, "covered": 0}
        importance_groups[importance]["total"] += 1
        if row.prefix in roa_prefixes:
            importance_groups[importance]["covered"] += 1

    by_importance: list[ROACoverageByImportance] = []
    for importance, counts in importance_groups.items():
        total = counts["total"]
        covered = counts["covered"]
        rate = covered / total if total > 0 else 0.0
        by_importance.append(
            ROACoverageByImportance(
                importance=importance,
                total_prefixes=total,
                covered_prefixes=covered,
                coverage_rate=rate,
            )
        )

    # 总覆盖率
    total_prefixes = len(all_prefixes)
    covered_prefixes = sum(
        1 for row in all_prefixes if row.prefix in roa_prefixes
    )
    coverage_rate = (
        covered_prefixes / total_prefixes if total_prefixes > 0 else 0.0
    )

    # 按验证状态统计 BGP 公告
    status_stmt = (
        select(
            BGPAnnouncement.rpki_validation_status,
            func.count(BGPAnnouncement.id),
        )
        .group_by(BGPAnnouncement.rpki_validation_status)
    )
    status_result = await db.execute(status_stmt)
    by_status: list[ROACoverageByStatus] = []
    for row in status_result:
        status = row.rpki_validation_status or "not_found"
        by_status.append(
            ROACoverageByStatus(
                validation_status=status,
                count=row.count,
            )
        )

    # 公告总数
    total_announcements_result = await db.execute(
        select(func.count(BGPAnnouncement.id))
    )
    total_announcements = total_announcements_result.scalar_one()

    return ROACoverageStats(
        total_prefixes=total_prefixes,
        covered_prefixes=covered_prefixes,
        coverage_rate=coverage_rate,
        total_announcements=total_announcements,
        by_importance=by_importance,
        by_status=by_status,
    )


# ──────────────────────────────────────────────
# ROA 健康度摘要
# ──────────────────────────────────────────────


async def get_roa_health_summary(db: AsyncSession) -> ROAHealthSummary:
    """获取 ROA 健康度摘要。

    汇总 ROA 的状态分布、覆盖率、缺失数、冲突数与高风险数。

    Args:
        db: 异步数据库会话

    Returns:
        ROA 健康度摘要
    """
    # ROA 状态分布
    status_stmt = (
        select(ROA.status, func.count(ROA.id))
        .group_by(ROA.status)
    )
    status_result = await db.execute(status_stmt)
    status_counts: dict[str, int] = {
        row.status: row.count for row in status_result
    }

    total_roas = sum(status_counts.values())
    valid_roas = status_counts.get("valid", 0)
    expired_roas = status_counts.get("expired", 0)
    revoked_roas = status_counts.get("revoked", 0)

    # 覆盖率统计
    coverage_stats = await get_roa_coverage_stats(db)
    coverage_rate = coverage_stats.coverage_rate

    # 缺失数
    missing_results = await roa_service.check_roa_missing(db)
    missing_count = len(missing_results)

    # 冲突数
    conflict_results = await roa_service.check_roa_conflict(db)
    conflict_count = len(conflict_results)

    # 高风险 ROA 数（maxLength 过宽）
    # 仅检查有效 ROA
    valid_roa_stmt = select(ROA.id).where(ROA.status == "valid")
    valid_roa_result = await db.execute(valid_roa_stmt)
    valid_roa_ids = [row.id for row in valid_roa_result]

    high_risk_count = 0
    for roa_id in valid_roa_ids:
        risk = await roa_service.check_max_length_risk(db, roa_id)
        if risk is not None and risk.risk_level in ("high", "medium"):
            high_risk_count += 1

    # 整体健康判定
    overall_healthy = (
        expired_roas == 0
        and conflict_count == 0
        and coverage_rate >= 0.8
        and high_risk_count == 0
    )

    return ROAHealthSummary(
        total_roas=total_roas,
        valid_roas=valid_roas,
        expired_roas=expired_roas,
        revoked_roas=revoked_roas,
        coverage_rate=coverage_rate,
        missing_count=missing_count,
        conflict_count=conflict_count,
        high_risk_count=high_risk_count,
        overall_healthy=overall_healthy,
        summary={
            "status_distribution": status_counts,
            "coverage_by_importance": [
                item.model_dump() for item in coverage_stats.by_importance
            ],
        },
    )


__all__ = [
    "get_roa_coverage_stats",
    "get_roa_health_summary",
    "validate_roa_against_bgp",
]
