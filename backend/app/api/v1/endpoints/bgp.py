"""BGP 数据采集 API 端点。

提供 BGP 数据源、观察点、公告、撤路、设备适配器的管理与查询接口。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.core.rbac import Permissions
from app.models.bgp import DeviceAdapter
from app.models.user import User
from app.schemas.bgp import (
    BGPAnnouncementQueryParams,
    BGPAnnouncementResponse,
    BGPDataSourceCreate,
    BGPDataSourceResponse,
    BGPDataSourceUpdate,
    BGPStatsResponse,
    BGPWithdrawQueryParams,
    BGPWithdrawResponse,
    DataSourceHealthResponse,
    DeviceAdapterCreate,
    DeviceAdapterResponse,
    DeviceAdapterUpdate,
    ObservationPointCreate,
    ObservationPointResponse,
    ObservationPointUpdate,
)
from app.services import bgp_collector_service, bgp_storage_service
from app.services.device_adapter_service import test_device_connection

router = APIRouter()


# ──────────────────────────────────────────────
# 数据源管理
# ──────────────────────────────────────────────


@router.post(
    "/data-sources",
    response_model=BGPDataSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_data_source(
    source_create: BGPDataSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> BGPDataSourceResponse:
    """创建 BGP 数据源（需要 ``bgp:write`` 权限）。"""
    data_source = await bgp_collector_service.create_data_source(db, source_create)
    return BGPDataSourceResponse.model_validate(data_source)


@router.get("/data-sources", response_model=list[BGPDataSourceResponse])
async def list_data_sources(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数上限"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    source_type: str | None = Query(None, description="按类型过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> list[BGPDataSourceResponse]:
    """获取数据源列表（需要 ``bgp:read`` 权限）。"""
    data_sources = await bgp_collector_service.get_data_sources(
        db, skip=skip, limit=limit, status=status_filter, source_type=source_type
    )
    return [BGPDataSourceResponse.model_validate(ds) for ds in data_sources]


@router.get("/data-sources/{source_id}", response_model=BGPDataSourceResponse)
async def get_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> BGPDataSourceResponse:
    """获取数据源详情（需要 ``bgp:read`` 权限）。"""
    data_source = await bgp_collector_service.get_data_source(db, source_id)
    if data_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {source_id} 不存在",
        )
    return BGPDataSourceResponse.model_validate(data_source)


@router.put("/data-sources/{source_id}", response_model=BGPDataSourceResponse)
async def update_data_source(
    source_id: int,
    source_update: BGPDataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> BGPDataSourceResponse:
    """更新数据源（需要 ``bgp:write`` 权限）。"""
    data_source = await bgp_collector_service.update_data_source(
        db, source_id, source_update
    )
    if data_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {source_id} 不存在",
        )
    return BGPDataSourceResponse.model_validate(data_source)


@router.delete("/data-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> None:
    """删除数据源（需要 ``bgp:write`` 权限）。"""
    deleted = await bgp_collector_service.delete_data_source(db, source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {source_id} 不存在",
        )


@router.post("/data-sources/{source_id}/start")
async def start_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> dict[str, Any]:
    """启动数据源采集（需要 ``bgp:write`` 权限）。"""
    task_id = await bgp_collector_service.start_data_source(db, source_id)
    if task_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {source_id} 不存在",
        )
    return {"source_id": source_id, "task_id": task_id, "status": "started"}


@router.post("/data-sources/{source_id}/stop")
async def stop_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> dict[str, Any]:
    """停止数据源采集（需要 ``bgp:write`` 权限）。"""
    stopped = await bgp_collector_service.stop_data_source(db, source_id)
    if not stopped:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {source_id} 不存在",
        )
    return {"source_id": source_id, "status": "stopped"}


@router.get(
    "/data-sources/{source_id}/health",
    response_model=DataSourceHealthResponse,
)
async def get_data_source_health(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> DataSourceHealthResponse:
    """获取数据源健康状态（需要 ``bgp:read`` 权限）。"""
    health = await bgp_collector_service.check_single_data_source_health(
        db, source_id
    )
    if health is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {source_id} 不存在",
        )
    return health


@router.get("/data-sources-health", response_model=list[DataSourceHealthResponse])
async def get_all_data_sources_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> list[DataSourceHealthResponse]:
    """获取所有数据源健康状态（需要 ``bgp:read`` 权限）。"""
    return await bgp_collector_service.check_data_source_health(db)


# ──────────────────────────────────────────────
# 观察点管理
# ──────────────────────────────────────────────


@router.get("/observation-points", response_model=list[ObservationPointResponse])
async def list_observation_points(
    data_source_id: int | None = Query(None, description="按数据源过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> list[ObservationPointResponse]:
    """获取观察点列表（需要 ``bgp:read`` 权限）。"""
    points = await bgp_collector_service.get_observation_points(
        db, data_source_id=data_source_id, skip=skip, limit=limit
    )
    return [ObservationPointResponse.model_validate(p) for p in points]


@router.post(
    "/observation-points",
    response_model=ObservationPointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_observation_point(
    point_create: ObservationPointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> ObservationPointResponse:
    """创建观察点（需要 ``bgp:write`` 权限）。"""
    point = await bgp_collector_service.create_observation_point(db, point_create)
    if point is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据源 ID {point_create.data_source_id} 不存在",
        )
    return ObservationPointResponse.model_validate(point)


@router.put(
    "/observation-points/{point_id}",
    response_model=ObservationPointResponse,
)
async def update_observation_point(
    point_id: int,
    point_update: ObservationPointUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> ObservationPointResponse:
    """更新观察点（需要 ``bgp:write`` 权限）。"""
    point = await bgp_collector_service.update_observation_point(
        db, point_id, point_update
    )
    if point is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"观察点 ID {point_id} 不存在",
        )
    return ObservationPointResponse.model_validate(point)


# ──────────────────────────────────────────────
# BGP 公告查询
# ──────────────────────────────────────────────


@router.get("/announcements", response_model=list[BGPAnnouncementResponse])
async def list_announcements(
    prefix: str | None = Query(None, description="按前缀过滤"),
    origin_as: int | None = Query(None, description="按起源 AS 过滤"),
    observation_point_id: int | None = Query(None, description="按观察点过滤"),
    data_source_id: int | None = Query(None, description="按数据源过滤"),
    start_time: datetime | None = Query(None, description="起始时间"),
    end_time: datetime | None = Query(None, description="截止时间"),
    rpki_validation_status: str | None = Query(
        None, description="按 RPKI 验证状态过滤"
    ),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> list[BGPAnnouncementResponse]:
    """查询 BGP 公告列表（需要 ``bgp:read`` 权限）。"""
    query_params = BGPAnnouncementQueryParams(
        prefix=prefix,
        origin_as=origin_as,
        observation_point_id=observation_point_id,
        data_source_id=data_source_id,
        start_time=start_time,
        end_time=end_time,
        rpki_validation_status=rpki_validation_status,
        skip=skip,
        limit=limit,
    )
    announcements = await bgp_storage_service.get_announcements(db, query_params)
    return [BGPAnnouncementResponse.model_validate(a) for a in announcements]


@router.get(
    "/announcements/{announcement_id}",
    response_model=BGPAnnouncementResponse,
)
async def get_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> BGPAnnouncementResponse:
    """获取 BGP 公告详情（需要 ``bgp:read`` 权限）。"""
    announcement = await bgp_storage_service.get_announcement_by_id(
        db, announcement_id
    )
    if announcement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"公告 ID {announcement_id} 不存在",
        )
    return BGPAnnouncementResponse.model_validate(announcement)


# ──────────────────────────────────────────────
# BGP 撤路查询
# ──────────────────────────────────────────────


@router.get("/withdraws", response_model=list[BGPWithdrawResponse])
async def list_withdraws(
    prefix: str | None = Query(None, description="按前缀过滤"),
    observation_point_id: int | None = Query(None, description="按观察点过滤"),
    data_source_id: int | None = Query(None, description="按数据源过滤"),
    start_time: datetime | None = Query(None, description="起始时间"),
    end_time: datetime | None = Query(None, description="截止时间"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> list[BGPWithdrawResponse]:
    """查询 BGP 撤路列表（需要 ``bgp:read`` 权限）。"""
    query_params = BGPWithdrawQueryParams(
        prefix=prefix,
        observation_point_id=observation_point_id,
        data_source_id=data_source_id,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )
    withdraws = await bgp_storage_service.get_withdraws(db, query_params)
    return [BGPWithdrawResponse.model_validate(w) for w in withdraws]


# ──────────────────────────────────────────────
# BGP 统计
# ──────────────────────────────────────────────


@router.get("/stats", response_model=BGPStatsResponse)
async def get_bgp_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> BGPStatsResponse:
    """获取 BGP 统计数据（需要 ``bgp:read`` 权限）。"""
    return await bgp_collector_service.get_bgp_stats(db)


# ──────────────────────────────────────────────
# 设备适配器管理
# ──────────────────────────────────────────────


@router.post(
    "/device-adapters",
    response_model=DeviceAdapterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_device_adapter(
    adapter_create: DeviceAdapterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> DeviceAdapterResponse:
    """创建设备适配器（需要 ``bgp:write`` 权限）。"""
    adapter = DeviceAdapter(
        name=adapter_create.name,
        vendor=adapter_create.vendor,
        model=adapter_create.model,
        connection_type=adapter_create.connection_type,
        endpoint=adapter_create.endpoint,
        credentials=adapter_create.credentials,
        capabilities=adapter_create.capabilities,
        status="disabled",
        tenant_id=adapter_create.tenant_id,
    )
    db.add(adapter)
    await db.flush()
    await db.commit()
    await db.refresh(adapter)
    return DeviceAdapterResponse.model_validate(adapter)


@router.get("/device-adapters", response_model=list[DeviceAdapterResponse])
async def list_device_adapters(
    vendor: str | None = Query(None, description="按厂商过滤"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> list[DeviceAdapterResponse]:
    """获取设备适配器列表（需要 ``bgp:read`` 权限）。"""
    stmt = select(DeviceAdapter)
    if vendor is not None:
        stmt = stmt.where(DeviceAdapter.vendor == vendor)
    if status_filter is not None:
        stmt = stmt.where(DeviceAdapter.status == status_filter)
    stmt = stmt.order_by(DeviceAdapter.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    adapters = list(result.scalars().all())
    return [DeviceAdapterResponse.model_validate(a) for a in adapters]


@router.get(
    "/device-adapters/{adapter_id}",
    response_model=DeviceAdapterResponse,
)
async def get_device_adapter(
    adapter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_READ)),
) -> DeviceAdapterResponse:
    """获取设备适配器详情（需要 ``bgp:read`` 权限）。"""
    stmt = select(DeviceAdapter).where(DeviceAdapter.id == adapter_id)
    result = await db.execute(stmt)
    adapter = result.scalar_one_or_none()
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备适配器 ID {adapter_id} 不存在",
        )
    return DeviceAdapterResponse.model_validate(adapter)


@router.put(
    "/device-adapters/{adapter_id}",
    response_model=DeviceAdapterResponse,
)
async def update_device_adapter(
    adapter_id: int,
    adapter_update: DeviceAdapterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> DeviceAdapterResponse:
    """更新设备适配器（需要 ``bgp:write`` 权限）。"""
    stmt = select(DeviceAdapter).where(DeviceAdapter.id == adapter_id)
    result = await db.execute(stmt)
    adapter = result.scalar_one_or_none()
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备适配器 ID {adapter_id} 不存在",
        )

    update_data = adapter_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(adapter, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(adapter)
    return DeviceAdapterResponse.model_validate(adapter)


@router.delete(
    "/device-adapters/{adapter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_device_adapter(
    adapter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> None:
    """删除设备适配器（需要 ``bgp:write`` 权限）。"""
    stmt = select(DeviceAdapter).where(DeviceAdapter.id == adapter_id)
    result = await db.execute(stmt)
    adapter = result.scalar_one_or_none()
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备适配器 ID {adapter_id} 不存在",
        )
    await db.delete(adapter)
    await db.commit()


@router.post("/device-adapters/{adapter_id}/test")
async def test_device_adapter(
    adapter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permissions.BGP_WRITE)),
) -> dict[str, Any]:
    """测试设备适配器连接（需要 ``bgp:write`` 权限）。"""
    stmt = select(DeviceAdapter).where(DeviceAdapter.id == adapter_id)
    result = await db.execute(stmt)
    adapter = result.scalar_one_or_none()
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备适配器 ID {adapter_id} 不存在",
        )

    config = {
        "endpoint": adapter.endpoint,
        "credentials": adapter.credentials or {},
        "connection_type": adapter.connection_type,
        "model": adapter.model,
    }

    test_result = await test_device_connection(adapter.vendor, config)

    # 更新适配器状态
    if test_result["success"]:
        adapter.status = "active"
        adapter.last_connected_at = datetime.utcnow()
        adapter.last_error = None
    else:
        adapter.status = "error"
        adapter.last_error = test_result.get("message")

    await db.flush()
    await db.commit()

    return test_result
