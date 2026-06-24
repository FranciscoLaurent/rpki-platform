"""BGP 邻居管理端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.bgp_peer import (
    BGPPeerCreate,
    BGPPeerListResponse,
    BGPPeerResponse,
    BGPPeerUpdate,
)
from app.services import bgp_peer_service

router = APIRouter()


@router.post(
    "",
    response_model=BGPPeerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bgp_peer(
    payload: BGPPeerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("bgp_peer:write")),
) -> BGPPeerResponse:
    """创建 BGP 邻居（需要 ``bgp_peer:write`` 权限）。"""
    try:
        peer = await bgp_peer_service.create_bgp_peer(db, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return BGPPeerResponse.model_validate(peer)


@router.get("", response_model=BGPPeerListResponse)
async def list_bgp_peers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    peer_ip: str | None = Query(None, description="按邻居 IP 过滤"),
    remote_asn: int | None = Query(None, description="按远端 ASN 过滤"),
    address_family: str | None = Query(None, description="按地址族过滤"),
    session_type: str | None = Query(None, description="按会话类型过滤"),
    session_state: str | None = Query(None, description="按会话状态过滤"),
    router_id: int | None = Query(None, description="按路由器 ID 过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("bgp_peer:read")),
) -> BGPPeerListResponse:
    """获取 BGP 邻居列表（需要 ``bgp_peer:read`` 权限）。"""
    filters: dict[str, object] = {}
    if peer_ip is not None:
        filters["peer_ip"] = peer_ip
    if remote_asn is not None:
        filters["remote_asn"] = remote_asn
    if address_family is not None:
        filters["address_family"] = address_family
    if session_type is not None:
        filters["session_type"] = session_type
    if session_state is not None:
        filters["session_state"] = session_state
    if router_id is not None:
        filters["router_id"] = router_id

    items = await bgp_peer_service.get_bgp_peers(db, filters=filters, skip=skip, limit=limit)
    total = await bgp_peer_service.count_bgp_peers(db, filters=filters)
    return BGPPeerListResponse(
        items=[BGPPeerResponse.model_validate(p) for p in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{peer_id}", response_model=BGPPeerResponse)
async def get_bgp_peer(
    peer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("bgp_peer:read")),
) -> BGPPeerResponse:
    """获取 BGP 邻居详情（需要 ``bgp_peer:read`` 权限）。"""
    peer = await bgp_peer_service.get_bgp_peer(db, peer_id)
    if peer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BGP 邻居 ID {peer_id} 不存在",
        )
    return BGPPeerResponse.model_validate(peer)


@router.put("/{peer_id}", response_model=BGPPeerResponse)
async def update_bgp_peer(
    peer_id: int,
    payload: BGPPeerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("bgp_peer:write")),
) -> BGPPeerResponse:
    """更新 BGP 邻居（需要 ``bgp_peer:write`` 权限）。"""
    peer = await bgp_peer_service.get_bgp_peer(db, peer_id)
    if peer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BGP 邻居 ID {peer_id} 不存在",
        )
    try:
        updated = await bgp_peer_service.update_bgp_peer(db, peer, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return BGPPeerResponse.model_validate(updated)


@router.delete("/{peer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bgp_peer(
    peer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("bgp_peer:write")),
) -> None:
    """删除 BGP 邻居（需要 ``bgp_peer:write`` 权限）。"""
    peer = await bgp_peer_service.get_bgp_peer(db, peer_id)
    if peer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BGP 邻居 ID {peer_id} 不存在",
        )
    await bgp_peer_service.delete_bgp_peer(db, peer)
