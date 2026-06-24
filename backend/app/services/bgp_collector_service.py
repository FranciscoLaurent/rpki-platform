"""BGP 数据采集服务。

管理 BGP 数据源的生命周期：创建、启动、停止、健康检查。
实际的采集逻辑由各数据源对应的采集器实现（RIS、RouteViews、BMP 等）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.models.bgp import (
    BGPAnnouncement,
    BGPDataSource,
    BGPWithdraw,
    DeviceAdapter,
    ObservationPoint,
)
from app.schemas.bgp import (
    BGPDataSourceCreate,
    BGPDataSourceUpdate,
    BGPStatsResponse,
    DataSourceHealthResponse,
    ObservationPointCreate,
    ObservationPointUpdate,
)

logger: BoundLogger = get_logger("app.bgp_collector")

# 运行中的采集任务注册表（内存态，进程级）
# 实际生产环境应使用 Redis 或任务队列管理
_running_tasks: dict[int, str] = {}


# ──────────────────────────────────────────────
# 数据源 CRUD
# ──────────────────────────────────────────────


async def create_data_source(
    db: AsyncSession,
    source_create: BGPDataSourceCreate,
) -> BGPDataSource:
    """创建 BGP 数据源。

    Args:
        db: 异步数据库会话
        source_create: 数据源创建参数

    Returns:
        创建的 BGPDataSource 对象
    """
    data_source = BGPDataSource(
        name=source_create.name,
        source_type=source_create.source_type,
        protocol=source_create.protocol,
        endpoint=source_create.endpoint,
        credentials=source_create.credentials,
        status="disabled",
        trust_level=source_create.trust_level,
        coverage=source_create.coverage,
        config=source_create.config,
        tenant_id=source_create.tenant_id,
    )
    db.add(data_source)
    await db.flush()
    await db.commit()
    await db.refresh(data_source)
    logger.info(
        "创建 BGP 数据源",
        source_id=data_source.id,
        name=data_source.name,
        source_type=data_source.source_type,
    )
    return data_source


async def get_data_source(
    db: AsyncSession,
    source_id: int,
) -> BGPDataSource | None:
    """根据 ID 获取数据源。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID

    Returns:
        BGPDataSource 对象，不存在则返回 None
    """
    stmt = select(BGPDataSource).where(BGPDataSource.id == source_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_data_sources(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    source_type: str | None = None,
) -> list[BGPDataSource]:
    """获取数据源列表。

    Args:
        db: 异步数据库会话
        skip: 跳过记录数
        limit: 返回记录数上限
        status: 按状态过滤
        source_type: 按类型过滤

    Returns:
        数据源列表
    """
    stmt = select(BGPDataSource)
    if status is not None:
        stmt = stmt.where(BGPDataSource.status == status)
    if source_type is not None:
        stmt = stmt.where(BGPDataSource.source_type == source_type)
    stmt = stmt.order_by(BGPDataSource.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_data_source(
    db: AsyncSession,
    source_id: int,
    source_update: BGPDataSourceUpdate,
) -> BGPDataSource | None:
    """更新数据源。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID
        source_update: 更新参数

    Returns:
        更新后的 BGPDataSource 对象，不存在则返回 None
    """
    data_source = await get_data_source(db, source_id)
    if data_source is None:
        return None

    update_data = source_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(data_source, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(data_source)
    logger.info("更新 BGP 数据源", source_id=source_id)
    return data_source


async def delete_data_source(
    db: AsyncSession,
    source_id: int,
) -> bool:
    """删除数据源。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID

    Returns:
        是否删除成功
    """
    data_source = await get_data_source(db, source_id)
    if data_source is None:
        return False

    # 停止运行中的采集任务
    if source_id in _running_tasks:
        await stop_data_source(db, source_id)

    await db.delete(data_source)
    await db.commit()
    logger.info("删除 BGP 数据源", source_id=source_id)
    return True


# ──────────────────────────────────────────────
# 数据源采集控制
# ──────────────────────────────────────────────


async def start_data_source(
    db: AsyncSession,
    source_id: int,
) -> str | None:
    """启动数据源采集。

    根据数据源类型选择对应的采集器并启动采集任务。
    当前为占位实现，返回任务 ID。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID

    Returns:
        任务 ID，数据源不存在则返回 None
    """
    data_source = await get_data_source(db, source_id)
    if data_source is None:
        return None

    # 生成任务 ID
    task_id = f"bgp-collect-{source_id}-{uuid.uuid4().hex[:8]}"

    # 更新数据源状态
    data_source.status = "active"
    data_source.last_connected_at = datetime.utcnow()
    data_source.last_error = None
    await db.flush()
    await db.commit()

    # 注册任务（占位）
    _running_tasks[source_id] = task_id

    logger.info(
        "启动 BGP 数据源采集",
        source_id=source_id,
        task_id=task_id,
        source_type=data_source.source_type,
    )

    # TODO: 根据数据源类型启动对应的采集器
    # - ripe_ris: 启动 RIPERisCollector
    # - routeviews: 启动 RouteViewsCollector
    # - bmp: 启动 BMPCollector
    # - route_server/commercial/internal: 启动 DeviceAdapter

    return task_id


async def stop_data_source(
    db: AsyncSession,
    source_id: int,
) -> bool:
    """停止数据源采集。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID

    Returns:
        是否停止成功
    """
    data_source = await get_data_source(db, source_id)
    if data_source is None:
        return False

    # 移除任务注册
    task_id = _running_tasks.pop(source_id, None)

    # 更新数据源状态
    data_source.status = "disabled"
    await db.flush()
    await db.commit()

    logger.info(
        "停止 BGP 数据源采集",
        source_id=source_id,
        task_id=task_id,
    )

    # TODO: 停止对应的采集器任务

    return True


async def get_data_source_status(
    db: AsyncSession,
    source_id: int,
) -> dict[str, Any] | None:
    """获取数据源状态。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID

    Returns:
        状态字典，数据源不存在则返回 None
    """
    data_source = await get_data_source(db, source_id)
    if data_source is None:
        return None

    return {
        "source_id": data_source.id,
        "name": data_source.name,
        "status": data_source.status,
        "source_type": data_source.source_type,
        "protocol": data_source.protocol,
        "is_running": source_id in _running_tasks,
        "task_id": _running_tasks.get(source_id),
        "last_connected_at": data_source.last_connected_at,
        "last_error": data_source.last_error,
        "trust_level": data_source.trust_level,
    }


# ──────────────────────────────────────────────
# 数据源健康检查
# ──────────────────────────────────────────────


async def check_data_source_health(
    db: AsyncSession,
) -> list[DataSourceHealthResponse]:
    """检查所有数据源的健康状态。

    Args:
        db: 异步数据库会话

    Returns:
        各数据源的健康状态列表
    """
    stmt = select(BGPDataSource)
    result = await db.execute(stmt)
    data_sources = list(result.scalars().all())

    health_list: list[DataSourceHealthResponse] = []
    for ds in data_sources:
        # 判断健康状态：active 且最近有连接时间视为健康
        healthy = ds.status == "active" and ds.last_error is None
        health_list.append(
            DataSourceHealthResponse(
                source_id=ds.id,
                name=ds.name,
                status=ds.status,
                healthy=healthy,
                last_connected_at=ds.last_connected_at,
                last_error=ds.last_error,
                trust_level=ds.trust_level,
            )
        )

    return health_list


async def check_single_data_source_health(
    db: AsyncSession,
    source_id: int,
) -> DataSourceHealthResponse | None:
    """检查单个数据源的健康状态。

    Args:
        db: 异步数据库会话
        source_id: 数据源 ID

    Returns:
        健康状态响应，数据源不存在则返回 None
    """
    data_source = await get_data_source(db, source_id)
    if data_source is None:
        return None

    healthy = data_source.status == "active" and data_source.last_error is None
    return DataSourceHealthResponse(
        source_id=data_source.id,
        name=data_source.name,
        status=data_source.status,
        healthy=healthy,
        last_connected_at=data_source.last_connected_at,
        last_error=data_source.last_error,
        trust_level=data_source.trust_level,
    )


# ──────────────────────────────────────────────
# 观察点管理
# ──────────────────────────────────────────────


async def create_observation_point(
    db: AsyncSession,
    point_create: ObservationPointCreate,
) -> ObservationPoint | None:
    """创建观察点。

    Args:
        db: 异步数据库会话
        point_create: 观察点创建参数

    Returns:
        创建的 ObservationPoint 对象，数据源不存在则返回 None
    """
    # 校验数据源存在
    data_source = await get_data_source(db, point_create.data_source_id)
    if data_source is None:
        return None

    observation_point = ObservationPoint(
        name=point_create.name,
        data_source_id=point_create.data_source_id,
        location=point_create.location,
        collector_id=point_create.collector_id,
        ip_version=point_create.ip_version,
        status=point_create.status,
    )
    db.add(observation_point)
    await db.flush()
    await db.commit()
    await db.refresh(observation_point)
    return observation_point


async def get_observation_points(
    db: AsyncSession,
    data_source_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ObservationPoint]:
    """获取观察点列表。

    Args:
        db: 异步数据库会话
        data_source_id: 按数据源过滤
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        观察点列表
    """
    stmt = select(ObservationPoint)
    if data_source_id is not None:
        stmt = stmt.where(ObservationPoint.data_source_id == data_source_id)
    stmt = stmt.order_by(ObservationPoint.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_observation_point(
    db: AsyncSession,
    point_id: int,
    point_update: ObservationPointUpdate,
) -> ObservationPoint | None:
    """更新观察点。

    Args:
        db: 异步数据库会话
        point_id: 观察点 ID
        point_update: 更新参数

    Returns:
        更新后的 ObservationPoint 对象，不存在则返回 None
    """
    stmt = select(ObservationPoint).where(ObservationPoint.id == point_id)
    result = await db.execute(stmt)
    observation_point = result.scalar_one_or_none()
    if observation_point is None:
        return None

    update_data = point_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(observation_point, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(observation_point)
    return observation_point


# ──────────────────────────────────────────────
# 统计
# ──────────────────────────────────────────────


async def get_bgp_stats(db: AsyncSession) -> BGPStatsResponse:
    """获取 BGP 统计数据。

    Args:
        db: 异步数据库会话

    Returns:
        BGP 统计数据响应
    """
    # 数据源统计
    total_sources_stmt = select(func.count(BGPDataSource.id))
    total_sources = (await db.execute(total_sources_stmt)).scalar_one()

    active_sources_stmt = select(func.count(BGPDataSource.id)).where(
        BGPDataSource.status == "active"
    )
    active_sources = (await db.execute(active_sources_stmt)).scalar_one()

    # 观察点统计
    total_points_stmt = select(func.count(ObservationPoint.id))
    total_points = (await db.execute(total_points_stmt)).scalar_one()

    # 公告统计
    total_announcements_stmt = select(func.count(BGPAnnouncement.id))
    total_announcements = (await db.execute(total_announcements_stmt)).scalar_one()

    # 撤路统计
    total_withdraws_stmt = select(func.count(BGPWithdraw.id))
    total_withdraws = (await db.execute(total_withdraws_stmt)).scalar_one()

    # 设备适配器统计
    total_adapters_stmt = select(func.count(DeviceAdapter.id))
    total_adapters = (await db.execute(total_adapters_stmt)).scalar_one()

    # 按 RPKI 验证状态分组统计公告
    rpki_stmt = select(
        BGPAnnouncement.rpki_validation_status,
        func.count(BGPAnnouncement.id),
    ).group_by(BGPAnnouncement.rpki_validation_status)
    rpki_result = await db.execute(rpki_stmt)
    announcements_by_rpki_status: dict[str, int] = {}
    for status_value, count in rpki_result.all():
        key = status_value if status_value is not None else "unknown"
        announcements_by_rpki_status[key] = count

    return BGPStatsResponse(
        total_data_sources=total_sources,
        active_data_sources=active_sources,
        total_observation_points=total_points,
        total_announcements=total_announcements,
        total_withdraws=total_withdraws,
        total_device_adapters=total_adapters,
        announcements_by_rpki_status=announcements_by_rpki_status,
    )
