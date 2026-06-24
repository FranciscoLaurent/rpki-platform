"""BGP 数据存储服务。

提供 BGP 公告、撤路与 RIB 快照的存储与查询功能。
热数据存储在 PostgreSQL，历史数据存储在 ClickHouse。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import BoundLogger

from app.core.clickhouse import ClickHouseService
from app.core.logging import get_logger
from app.models.bgp import (
    BGPAnnouncement,
    BGPRibSnapshot,
    BGPWithdraw,
)
from app.schemas.bgp import BGPAnnouncementQueryParams, BGPWithdrawQueryParams

logger: BoundLogger = get_logger("app.bgp_storage")


# ──────────────────────────────────────────────
# 公告存储
# ──────────────────────────────────────────────


async def store_announcement(
    db: AsyncSession,
    announcement: dict[str, Any],
) -> BGPAnnouncement:
    """存储 BGP 公告到 PostgreSQL（热数据）。

    Args:
        db: 异步数据库会话
        announcement: 公告数据字典，包含 prefix、origin_as、as_path 等字段

    Returns:
        创建的 BGPAnnouncement 对象
    """
    record = BGPAnnouncement(
        prefix=announcement["prefix"],
        prefix_family=announcement.get("prefix_family", 4),
        prefix_length=announcement.get("prefix_length", 0),
        origin_as=announcement.get("origin_as"),
        as_path=announcement.get("as_path"),
        next_hop=announcement.get("next_hop"),
        communities=announcement.get("communities"),
        large_communities=announcement.get("large_communities"),
        med=announcement.get("med"),
        local_pref=announcement.get("local_pref"),
        observation_point_id=announcement.get("observation_point_id"),
        data_source_id=announcement.get("data_source_id"),
        timestamp=announcement.get("timestamp", datetime.utcnow()),
        address_family=announcement.get("address_family", 4),
        rpki_validation_status=announcement.get("rpki_validation_status"),
        rpki_invalid_reason=announcement.get("rpki_invalid_reason"),
        tenant_id=announcement.get("tenant_id"),
    )
    db.add(record)
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return record


def store_announcement_to_clickhouse(
    ch: ClickHouseService,
    announcement: dict[str, Any],
) -> None:
    """存储 BGP 公告到 ClickHouse（历史数据）。

    ClickHouse 表结构见 ``app/core/sql/bgp_announcements.sql``。

    Args:
        ch: ClickHouse 服务实例
        announcement: 公告数据字典
    """
    timestamp = announcement.get("timestamp", datetime.utcnow())
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    data = [
        [
            announcement.get("prefix", ""),
            int(announcement.get("origin_as", 0) or 0),
            announcement.get("as_path", []) or [],
            announcement.get("next_hop", ""),
            announcement.get("communities", []) or [],
            str(announcement.get("observation_point_id", "")),
            timestamp,
        ]
    ]
    column_names = [
        "prefix",
        "origin_as",
        "as_path",
        "next_hop",
        "communities",
        "observation_point",
        "timestamp",
    ]
    ch.insert("bgp_announcements", data, column_names)


async def store_announcements_batch(
    db: AsyncSession,
    announcements: list[dict[str, Any]],
) -> list[BGPAnnouncement]:
    """批量存储 BGP 公告。

    Args:
        db: 异步数据库会话
        announcements: 公告数据字典列表

    Returns:
        创建的 BGPAnnouncement 对象列表
    """
    records: list[BGPAnnouncement] = []
    for announcement in announcements:
        record = BGPAnnouncement(
            prefix=announcement["prefix"],
            prefix_family=announcement.get("prefix_family", 4),
            prefix_length=announcement.get("prefix_length", 0),
            origin_as=announcement.get("origin_as"),
            as_path=announcement.get("as_path"),
            next_hop=announcement.get("next_hop"),
            communities=announcement.get("communities"),
            large_communities=announcement.get("large_communities"),
            med=announcement.get("med"),
            local_pref=announcement.get("local_pref"),
            observation_point_id=announcement.get("observation_point_id"),
            data_source_id=announcement.get("data_source_id"),
            timestamp=announcement.get("timestamp", datetime.utcnow()),
            address_family=announcement.get("address_family", 4),
            rpki_validation_status=announcement.get("rpki_validation_status"),
            rpki_invalid_reason=announcement.get("rpki_invalid_reason"),
            tenant_id=announcement.get("tenant_id"),
        )
        records.append(record)
        db.add(record)

    await db.flush()
    await db.commit()
    return records


# ──────────────────────────────────────────────
# 撤路存储
# ──────────────────────────────────────────────


async def store_withdraw(
    db: AsyncSession,
    withdraw: dict[str, Any],
) -> BGPWithdraw:
    """存储 BGP 撤路记录。

    Args:
        db: 异步数据库会话
        withdraw: 撤路数据字典

    Returns:
        创建的 BGPWithdraw 对象
    """
    record = BGPWithdraw(
        prefix=withdraw["prefix"],
        prefix_family=withdraw.get("prefix_family", 4),
        prefix_length=withdraw.get("prefix_length", 0),
        observation_point_id=withdraw.get("observation_point_id"),
        data_source_id=withdraw.get("data_source_id"),
        timestamp=withdraw.get("timestamp", datetime.utcnow()),
        tenant_id=withdraw.get("tenant_id"),
    )
    db.add(record)
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return record


# ──────────────────────────────────────────────
# RIB 快照存储
# ──────────────────────────────────────────────


async def store_rib_snapshot(
    db: AsyncSession,
    snapshot_data: dict[str, Any],
) -> BGPRibSnapshot:
    """存储 RIB 快照元信息。

    Args:
        db: 异步数据库会话
        snapshot_data: 快照数据字典

    Returns:
        创建的 BGPRibSnapshot 对象
    """
    record = BGPRibSnapshot(
        observation_point_id=snapshot_data.get("observation_point_id"),
        snapshot_time=snapshot_data.get("snapshot_time", datetime.utcnow()),
        route_count=snapshot_data.get("route_count", 0),
        status=snapshot_data.get("status", "completed"),
    )
    db.add(record)
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return record


# ──────────────────────────────────────────────
# 公告查询
# ──────────────────────────────────────────────


async def get_announcements(
    db: AsyncSession,
    query_params: BGPAnnouncementQueryParams,
) -> list[BGPAnnouncement]:
    """查询 BGP 公告列表。

    支持按前缀、起源 AS、观察点、时间范围、RPKI 验证状态过滤。

    Args:
        db: 异步数据库会话
        query_params: 查询参数

    Returns:
        BGP 公告列表
    """
    stmt = select(BGPAnnouncement)

    if query_params.prefix is not None:
        stmt = stmt.where(BGPAnnouncement.prefix == query_params.prefix)
    if query_params.origin_as is not None:
        stmt = stmt.where(BGPAnnouncement.origin_as == query_params.origin_as)
    if query_params.observation_point_id is not None:
        stmt = stmt.where(
            BGPAnnouncement.observation_point_id == query_params.observation_point_id
        )
    if query_params.data_source_id is not None:
        stmt = stmt.where(
            BGPAnnouncement.data_source_id == query_params.data_source_id
        )
    if query_params.start_time is not None:
        stmt = stmt.where(BGPAnnouncement.timestamp >= query_params.start_time)
    if query_params.end_time is not None:
        stmt = stmt.where(BGPAnnouncement.timestamp <= query_params.end_time)
    if query_params.rpki_validation_status is not None:
        stmt = stmt.where(
            BGPAnnouncement.rpki_validation_status
            == query_params.rpki_validation_status
        )

    stmt = (
        stmt.order_by(BGPAnnouncement.timestamp.desc())
        .offset(query_params.skip)
        .limit(query_params.limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_announcement_by_id(
    db: AsyncSession,
    announcement_id: int,
) -> BGPAnnouncement | None:
    """根据 ID 获取 BGP 公告。

    Args:
        db: 异步数据库会话
        announcement_id: 公告 ID

    Returns:
        BGPAnnouncement 对象，不存在则返回 None
    """
    stmt = select(BGPAnnouncement).where(BGPAnnouncement.id == announcement_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def count_announcements(
    db: AsyncSession,
    query_params: BGPAnnouncementQueryParams | None = None,
) -> int:
    """统计 BGP 公告数量。

    Args:
        db: 异步数据库会话
        query_params: 查询参数（可选）

    Returns:
        公告数量
    """
    stmt = select(func.count(BGPAnnouncement.id))

    if query_params is not None:
        if query_params.prefix is not None:
            stmt = stmt.where(BGPAnnouncement.prefix == query_params.prefix)
        if query_params.origin_as is not None:
            stmt = stmt.where(BGPAnnouncement.origin_as == query_params.origin_as)
        if query_params.observation_point_id is not None:
            stmt = stmt.where(
                BGPAnnouncement.observation_point_id
                == query_params.observation_point_id
            )
        if query_params.data_source_id is not None:
            stmt = stmt.where(
                BGPAnnouncement.data_source_id == query_params.data_source_id
            )
        if query_params.start_time is not None:
            stmt = stmt.where(BGPAnnouncement.timestamp >= query_params.start_time)
        if query_params.end_time is not None:
            stmt = stmt.where(BGPAnnouncement.timestamp <= query_params.end_time)
        if query_params.rpki_validation_status is not None:
            stmt = stmt.where(
                BGPAnnouncement.rpki_validation_status
                == query_params.rpki_validation_status
            )

    result = await db.execute(stmt)
    return result.scalar_one()


# ──────────────────────────────────────────────
# 撤路查询
# ──────────────────────────────────────────────


async def get_withdraws(
    db: AsyncSession,
    query_params: BGPWithdrawQueryParams,
) -> list[BGPWithdraw]:
    """查询 BGP 撤路列表。

    Args:
        db: 异步数据库会话
        query_params: 查询参数

    Returns:
        BGP 撤路列表
    """
    stmt = select(BGPWithdraw)

    if query_params.prefix is not None:
        stmt = stmt.where(BGPWithdraw.prefix == query_params.prefix)
    if query_params.observation_point_id is not None:
        stmt = stmt.where(
            BGPWithdraw.observation_point_id == query_params.observation_point_id
        )
    if query_params.data_source_id is not None:
        stmt = stmt.where(BGPWithdraw.data_source_id == query_params.data_source_id)
    if query_params.start_time is not None:
        stmt = stmt.where(BGPWithdraw.timestamp >= query_params.start_time)
    if query_params.end_time is not None:
        stmt = stmt.where(BGPWithdraw.timestamp <= query_params.end_time)

    stmt = (
        stmt.order_by(BGPWithdraw.timestamp.desc())
        .offset(query_params.skip)
        .limit(query_params.limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_withdraws(db: AsyncSession) -> int:
    """统计 BGP 撤路总数。

    Args:
        db: 异步数据库会话

    Returns:
        撤路数量
    """
    stmt = select(func.count(BGPWithdraw.id))
    result = await db.execute(stmt)
    return result.scalar_one()


# ──────────────────────────────────────────────
# 去重与聚合
# ──────────────────────────────────────────────


def deduplicate_announcements(
    announcements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对公告列表去重。

    去重键为 ``(prefix, origin_as, observation_point_id)``。
    保留最新时间戳的公告。

    Args:
        announcements: 公告字典列表

    Returns:
        去重后的公告列表
    """
    seen: dict[tuple, dict[str, Any]] = {}

    for ann in announcements:
        key = (
            ann.get("prefix"),
            ann.get("origin_as"),
            ann.get("observation_point_id"),
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = ann
        else:
            # 保留时间戳更新的记录
            existing_ts = existing.get("timestamp")
            current_ts = ann.get("timestamp")
            if existing_ts is None or (
                current_ts is not None and current_ts > existing_ts
            ):
                seen[key] = ann

    return list(seen.values())


def aggregate_announcements(
    announcements: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """按前缀聚合公告。

    将公告按前缀分组，每组按起源 AS 再分组。

    Args:
        announcements: 公告字典列表

    Returns:
        聚合后的字典，键为前缀，值为该前缀下的公告列表
    """
    aggregated: dict[str, list[dict[str, Any]]] = {}

    for ann in announcements:
        prefix = ann.get("prefix", "")
        if prefix not in aggregated:
            aggregated[prefix] = []
        aggregated[prefix].append(ann)

    return aggregated


def aggregate_by_origin_as(
    announcements: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """按起源 AS 聚合公告。

    Args:
        announcements: 公告字典列表

    Returns:
        聚合后的字典，键为起源 AS，值为该 AS 的公告列表
    """
    aggregated: dict[int, list[dict[str, Any]]] = {}

    for ann in announcements:
        origin_as = ann.get("origin_as")
        if origin_as is None:
            continue
        if origin_as not in aggregated:
            aggregated[origin_as] = []
        aggregated[origin_as].append(ann)

    return aggregated
