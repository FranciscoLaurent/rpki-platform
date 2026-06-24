"""RPKI 健康检查服务。

提供仓库同步状态、缓存状态与单个仓库健康检查功能。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rpki import RPKICache, RPKIRepository
from app.schemas.rpki import (
    RepositoryHealthResponse,
    RPKIHealthResponse,
    SyncStatusResponse,
)

logger = get_logger("app.rpki_health_service")


# 同步过期阈值（小时）
SYNC_STALE_THRESHOLD_HOURS = 24


async def get_sync_status(db: AsyncSession) -> list[SyncStatusResponse]:
    """获取所有仓库的同步状态。

    Args:
        db: 异步数据库会话

    Returns:
        同步状态响应列表
    """
    stmt = select(RPKIRepository).order_by(RPKIRepository.id)
    result = await db.execute(stmt)
    repositories = list(result.scalars().all())

    statuses: list[SyncStatusResponse] = []
    for repo in repositories:
        # 计算进度（占位：基于状态推断）
        if repo.sync_status == "success":
            progress = 100.0
        elif repo.sync_status == "running":
            progress = 50.0
        elif repo.sync_status == "failed":
            progress = 0.0
        else:
            progress = 0.0

        statuses.append(
            SyncStatusResponse(
                tal_id=repo.tal_id,
                status=repo.sync_status,
                progress=progress,
                last_synced_at=repo.last_synced_at,
                error=repo.last_error,
            )
        )

    return statuses


async def get_cache_status(db: AsyncSession) -> dict[str, Any]:
    """获取 RPKI 缓存状态。

    Args:
        db: 异步数据库会话

    Returns:
        缓存状态字典，包含缓存列表与统计信息
    """
    stmt = select(RPKICache).order_by(RPKICache.id)
    result = await db.execute(stmt)
    caches = list(result.scalars().all())

    cache_list = [
        {
            "id": c.id,
            "name": c.name,
            "version": c.version,
            "vrp_count": c.vrp_count,
            "last_updated": c.last_updated.isoformat() if c.last_updated else None,
            "status": c.status,
        }
        for c in caches
    ]

    healthy_count = sum(1 for c in caches if c.status == "healthy")
    stale_count = sum(1 for c in caches if c.status == "stale")

    return {
        "caches": cache_list,
        "total": len(caches),
        "healthy_count": healthy_count,
        "stale_count": stale_count,
        "overall_healthy": stale_count == 0,
    }


async def check_repository_health(db: AsyncSession, repository_id: int) -> RepositoryHealthResponse:
    """检查单个仓库的健康状态。

    健康判定标准：
    - 同步状态为 success
    - 最近一次同步时间在 24 小时内
    - 无错误信息

    Args:
        db: 异步数据库会话
        repository_id: 仓库 ID

    Returns:
        仓库健康状态响应

    Raises:
        ValueError: 仓库不存在
    """
    stmt = select(RPKIRepository).where(RPKIRepository.id == repository_id)
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()
    if repo is None:
        raise ValueError(f"仓库 ID {repository_id} 不存在")

    # 判定健康状态
    is_healthy = True
    now = datetime.now(UTC)

    if repo.sync_status == "failed":
        is_healthy = False
    elif repo.sync_status == "running":
        # 同步中视为健康（进行中）
        is_healthy = True
    elif repo.last_synced_at is None:
        is_healthy = False
    else:
        # 检查同步新鲜度
        last_synced = repo.last_synced_at
        if last_synced.tzinfo is None:
            last_synced = last_synced.replace(tzinfo=UTC)
        delta_hours = (now - last_synced).total_seconds() / 3600
        if delta_hours > SYNC_STALE_THRESHOLD_HOURS:
            is_healthy = False

    return RepositoryHealthResponse(
        repository_id=repo.id,
        status=repo.status,
        sync_status=repo.sync_status,
        last_synced_at=repo.last_synced_at,
        object_count=repo.object_count,
        last_error=repo.last_error,
        is_healthy=is_healthy,
    )


async def get_overall_health(db: AsyncSession) -> RPKIHealthResponse:
    """获取 RPKI 整体健康状态。

    Args:
        db: 异步数据库会话

    Returns:
        RPKI 整体健康状态响应
    """
    stmt = select(RPKIRepository).order_by(RPKIRepository.id)
    result = await db.execute(stmt)
    repositories = list(result.scalars().all())

    repo_health_list: list[RepositoryHealthResponse] = []
    healthy_count = 0
    failed_count = 0

    for repo in repositories:
        try:
            health = await check_repository_health(db, repo.id)
            repo_health_list.append(health)
            if health.is_healthy:
                healthy_count += 1
            else:
                failed_count += 1
        except ValueError:
            failed_count += 1

    cache_status = await get_cache_status(db)
    overall_healthy = failed_count == 0 and cache_status.get("overall_healthy", True)

    return RPKIHealthResponse(
        overall_healthy=overall_healthy,
        total_repositories=len(repositories),
        healthy_repositories=healthy_count,
        failed_repositories=failed_count,
        repositories=repo_health_list,
        cache_status=cache_status,
    )
