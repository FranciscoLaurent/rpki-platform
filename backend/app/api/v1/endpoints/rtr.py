"""RPKI-RTR 服务管理 API 端点。

提供 RTR 服务的 CRUD、启动/停止、VRP 更新、序列号回滚、
一致性检查、客户端会话查询与序列号历史查询等接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.rtr import (
    RTRConsistencyCheckResult,
    RTRRollbackRequest,
    RTRSerialHistoryListResponse,
    RTRSerialHistoryResponse,
    RTRServerActionResponse,
    RTRServerCreate,
    RTRServerListResponse,
    RTRServerResponse,
    RTRServerStatus,
    RTRServerUpdate,
    RTRSessionListResponse,
    RTRSessionResponse,
)
from app.services import rtr_service

router = APIRouter()

# RTR 权限码（与 RBAC 系统约定，使用字符串字面量避免修改共享的 rbac.py）
RTR_READ = "rtr:read"
RTR_WRITE = "rtr:write"


# ──────────────────────────────────────────────
# RTR 服务 CRUD
# ──────────────────────────────────────────────


@router.post(
    "/servers",
    response_model=RTRServerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rtr_server(
    payload: RTRServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerResponse:
    """创建 RTR 服务（需要 ``rtr:write`` 权限）。"""
    try:
        server = await rtr_service.create_rtr_server(db, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return RTRServerResponse.model_validate(server)


@router.get("/servers", response_model=RTRServerListResponse)
async def list_rtr_servers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    server_status: str | None = Query(None, alias="status", description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> RTRServerListResponse:
    """获取 RTR 服务列表（需要 ``rtr:read`` 权限）。"""
    servers = await rtr_service.get_rtr_servers(db, skip=skip, limit=limit, status=server_status)
    total = await rtr_service.count_rtr_servers(db, status=server_status)
    return RTRServerListResponse(
        items=[RTRServerResponse.model_validate(s) for s in servers],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/servers/{server_id}", response_model=RTRServerResponse)
async def get_rtr_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> RTRServerResponse:
    """获取 RTR 服务详情（需要 ``rtr:read`` 权限）。"""
    server = await rtr_service.get_rtr_server(db, server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RTR 服务 ID {server_id} 不存在",
        )
    return RTRServerResponse.model_validate(server)


@router.put("/servers/{server_id}", response_model=RTRServerResponse)
async def update_rtr_server(
    server_id: int,
    payload: RTRServerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerResponse:
    """更新 RTR 服务（需要 ``rtr:write`` 权限）。"""
    server = await rtr_service.update_rtr_server(db, server_id, payload)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RTR 服务 ID {server_id} 不存在",
        )
    return RTRServerResponse.model_validate(server)


@router.delete(
    "/servers/{server_id}",
    response_model=RTRServerActionResponse,
)
async def delete_rtr_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerActionResponse:
    """删除 RTR 服务（需要 ``rtr:write`` 权限）。

    若服务正在运行，会先停止。
    """
    deleted = await rtr_service.delete_rtr_server(db, server_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RTR 服务 ID {server_id} 不存在",
        )
    return RTRServerActionResponse(
        server_id=server_id,
        status="deleted",
        message=f"RTR 服务 {server_id} 已删除",
        serial_number=None,
    )


# ──────────────────────────────────────────────
# RTR 服务生命周期
# ──────────────────────────────────────────────


@router.post(
    "/servers/{server_id}/start",
    response_model=RTRServerActionResponse,
)
async def start_rtr_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerActionResponse:
    """启动 RTR 服务（需要 ``rtr:write`` 权限）。"""
    try:
        server = await rtr_service.start_rtr_server(db, server_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    return RTRServerActionResponse(
        server_id=server_id,
        status=server.status,
        message=f"RTR 服务 {server_id} 已启动",
        serial_number=server.current_serial,
    )


@router.post(
    "/servers/{server_id}/stop",
    response_model=RTRServerActionResponse,
)
async def stop_rtr_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerActionResponse:
    """停止 RTR 服务（需要 ``rtr:write`` 权限）。"""
    try:
        server = await rtr_service.stop_rtr_server(db, server_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    return RTRServerActionResponse(
        server_id=server_id,
        status=server.status,
        message=f"RTR 服务 {server_id} 已停止",
        serial_number=server.current_serial,
    )


@router.get(
    "/servers/{server_id}/status",
    response_model=RTRServerStatus,
)
async def get_rtr_server_status(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> RTRServerStatus:
    """获取 RTR 服务运行状态（需要 ``rtr:read`` 权限）。"""
    try:
        return await rtr_service.get_rtr_server_status(db, server_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# VRP 更新与回滚
# ──────────────────────────────────────────────


@router.post(
    "/servers/{server_id}/update-vrps",
    response_model=RTRServerActionResponse,
)
async def update_vrps(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerActionResponse:
    """更新 RTR 服务的 VRP 数据（需要 ``rtr:write`` 权限）。

    从数据库加载最新 VRP，递增序列号并通知所有连接的客户端。
    """
    try:
        server = await rtr_service.update_vrps(db, server_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    return RTRServerActionResponse(
        server_id=server_id,
        status=server.status,
        message=f"RTR 服务 {server_id} VRP 数据已更新",
        serial_number=server.current_serial,
    )


@router.post(
    "/servers/{server_id}/rollback",
    response_model=RTRServerActionResponse,
)
async def rollback_serial(
    server_id: int,
    payload: RTRRollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> RTRServerActionResponse:
    """回滚 RTR 服务序列号（需要 ``rtr:write`` 权限）。"""
    try:
        server = await rtr_service.rollback_serial(db, server_id, payload.target_serial)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    return RTRServerActionResponse(
        server_id=server_id,
        status=server.status,
        message=(f"RTR 服务 {server_id} 已回滚到序列号 {payload.target_serial}"),
        serial_number=server.current_serial,
    )


# ──────────────────────────────────────────────
# 一致性检查
# ──────────────────────────────────────────────


@router.get(
    "/servers/{server_id}/consistency-check",
    response_model=RTRConsistencyCheckResult,
)
async def check_consistency(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> RTRConsistencyCheckResult:
    """一致性检查（需要 ``rtr:read`` 权限）。

    比较服务端内存中的 VRP 与数据库 VRP 的一致性。
    """
    try:
        return await rtr_service.check_consistency(db, server_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# 客户端会话与序列号历史
# ──────────────────────────────────────────────


@router.get(
    "/servers/{server_id}/sessions",
    response_model=RTRSessionListResponse,
)
async def get_rtr_sessions(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> RTRSessionListResponse:
    """获取 RTR 服务的客户端会话列表（需要 ``rtr:read`` 权限）。"""
    # 检查服务是否存在
    server = await rtr_service.get_rtr_server(db, server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RTR 服务 ID {server_id} 不存在",
        )
    sessions = await rtr_service.get_rtr_sessions(db, server_id)
    return RTRSessionListResponse(
        items=[RTRSessionResponse.model_validate(s) for s in sessions],
        total=len(sessions),
    )


@router.get(
    "/servers/{server_id}/serial-history",
    response_model=RTRSerialHistoryListResponse,
)
async def get_serial_history(
    server_id: int,
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> RTRSerialHistoryListResponse:
    """获取 RTR 服务的序列号历史（需要 ``rtr:read`` 权限）。"""
    # 检查服务是否存在
    server = await rtr_service.get_rtr_server(db, server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RTR 服务 ID {server_id} 不存在",
        )
    history = await rtr_service.get_serial_history(db, server_id, limit=limit)
    return RTRSerialHistoryListResponse(
        items=[RTRSerialHistoryResponse.model_validate(h) for h in history],
        total=len(history),
    )


__all__ = ["router"]
