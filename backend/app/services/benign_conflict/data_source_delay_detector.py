"""数据源延迟识别检测器。

识别 RPKI 数据源延迟或验证器不一致导致的良性冲突。

检测流程：
1. 检查多验证器差异（本地 VRP 与外部验证器对比）
2. 检查同步状态（TAL/Repository 同步状态）
3. 检查仓库对象时间戳

注意：良性冲突识别只降低误报优先级，不能替代安全验证。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import Alert
from app.models.rpki import TAL, VRP, RPKIRepository
from app.schemas.benign_conflict import BenignConflictAnalysisResult

logger = get_logger("app.benign_conflict.data_source_delay")


async def detect_data_source_delay(db: AsyncSession, alert: Alert) -> BenignConflictAnalysisResult:
    """识别 RPKI 数据源延迟。

    Args:
        db: 异步数据库会话
        alert: 待分析的告警对象

    Returns:
        良性冲突分析结果。若识别为数据源延迟，``is_benign`` 为 True，
        ``conflict_type`` 为 ``data_source_delay``。
    """
    prefix = alert.prefix
    origin_as = alert.origin_as

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "checks": {},
    }
    confidence = 0.0

    # 1. 检查同步状态（TAL/Repository）
    sync_status = await _check_sync_status(db)
    evidence["sync_status"] = sync_status
    if sync_status["has_failed_repositories"]:
        evidence["checks"]["has_failed_repositories"] = True
        confidence += 0.3
    if sync_status["has_stale_repositories"]:
        evidence["checks"]["has_stale_repositories"] = True
        confidence += 0.2

    # 2. 检查 VRP 数据新鲜度
    vrp_freshness = await _check_vrp_freshness(db, prefix, origin_as)
    evidence["vrp_freshness"] = vrp_freshness
    if vrp_freshness["is_stale"]:
        evidence["checks"]["vrp_is_stale"] = True
        confidence += 0.3

    # 3. 检查多验证器差异（占位，需对接外部验证器）
    evidence["checks"]["validator_comparison"] = "not_implemented"

    # 4. 检查仓库对象时间戳
    repo_timestamps = await _check_repository_timestamps(db)
    evidence["repository_timestamps"] = repo_timestamps
    if repo_timestamps["has_old_objects"]:
        evidence["checks"]["has_old_objects"] = True
        confidence += 0.1

    # 规范化置信度
    confidence = max(0.0, min(1.0, confidence))

    # 判定：存在同步失败或 VRP 数据陈旧 → 疑似良性冲突
    is_benign = (
        sync_status["has_failed_repositories"]
        or sync_status["has_stale_repositories"]
        or vrp_freshness["is_stale"]
    )

    if is_benign:
        recommendation = (
            f"前缀 {prefix} 的告警可能与 RPKI 数据源延迟有关，"
            "存在同步失败、数据陈旧或验证器不一致的情况。"
            "建议：检查 RPKI 仓库同步状态，"
            "触发手动同步并对比多验证器结果；"
            "在数据源恢复一致前，可暂时降低该类告警优先级。"
        )
    else:
        recommendation = "未识别为数据源延迟良性冲突，按正常告警处置流程处理。"

    return BenignConflictAnalysisResult(
        conflict_type="data_source_delay" if is_benign else None,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
        is_benign=is_benign,
    )


async def _check_sync_status(db: AsyncSession) -> dict[str, Any]:
    """检查 TAL 与仓库的同步状态。

    Args:
        db: 异步数据库会话

    Returns:
        包含同步状态信息的字典
    """
    # 查询 TAL 同步状态
    tal_stmt = select(TAL)
    tal_result = await db.execute(tal_stmt)
    tals = list(tal_result.scalars().all())

    # 查询仓库同步状态
    repo_stmt = select(RPKIRepository)
    repo_result = await db.execute(repo_stmt)
    repositories = list(repo_result.scalars().all())

    now = datetime.now(UTC)
    stale_threshold = timedelta(hours=1)

    failed_repos = [
        {"id": r.id, "uri": r.uri, "sync_status": r.sync_status, "last_error": r.last_error}
        for r in repositories
        if r.sync_status == "failed"
    ]

    stale_repos = []
    for r in repositories:
        if r.last_synced_at is not None:
            if now - r.last_synced_at > stale_threshold:
                stale_repos.append(
                    {
                        "id": r.id,
                        "uri": r.uri,
                        "last_synced_at": r.last_synced_at.isoformat(),
                        "stale_seconds": (now - r.last_synced_at).total_seconds(),
                    }
                )

    return {
        "total_tals": len(tals),
        "total_repositories": len(repositories),
        "has_failed_repositories": len(failed_repos) > 0,
        "has_stale_repositories": len(stale_repos) > 0,
        "failed_repositories": failed_repos[:5],
        "stale_repositories": stale_repos[:5],
    }


async def _check_vrp_freshness(
    db: AsyncSession, prefix: str, origin_as: int | None
) -> dict[str, Any]:
    """检查 VRP 数据新鲜度。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        origin_as: 起源 AS 号

    Returns:
        包含新鲜度信息的字典
    """
    now = datetime.now(UTC)
    stale_threshold = timedelta(hours=1)

    stmt = select(VRP).where(VRP.prefix == prefix)
    if origin_as is not None:
        stmt = stmt.where(VRP.origin_as == origin_as)

    result = await db.execute(stmt)
    vrps = list(result.scalars().all())

    if not vrps:
        return {
            "has_vrps": False,
            "is_stale": False,
            "vrp_count": 0,
            "message": "未找到匹配的 VRP",
        }

    latest_vrp = max(vrps, key=lambda v: v.updated_at or v.created_at)
    latest_time = latest_vrp.updated_at or latest_vrp.created_at
    is_stale = (now - latest_time) > stale_threshold

    return {
        "has_vrps": True,
        "is_stale": is_stale,
        "vrp_count": len(vrps),
        "latest_updated_at": latest_time.isoformat() if latest_time else None,
        "stale_seconds": (now - latest_time).total_seconds() if latest_time else None,
    }


async def _check_repository_timestamps(db: AsyncSession) -> dict[str, Any]:
    """检查仓库对象时间戳。

    Args:
        db: 异步数据库会话

    Returns:
        包含时间戳检查结果的字典
    """
    now = datetime.now(UTC)
    old_threshold = timedelta(hours=24)

    stmt = select(RPKIRepository.last_synced_at).where(RPKIRepository.last_synced_at.is_not(None))
    result = await db.execute(stmt)
    timestamps = [row[0] for row in result.all() if row[0] is not None]

    old_count = sum(1 for ts in timestamps if (now - ts) > old_threshold)

    return {
        "total_checked": len(timestamps),
        "old_count": old_count,
        "has_old_objects": old_count > 0,
        "threshold_hours": old_threshold.total_seconds() / 3600,
    }


__all__ = ["detect_data_source_delay"]
