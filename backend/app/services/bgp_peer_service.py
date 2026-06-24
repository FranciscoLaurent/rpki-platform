"""BGP 邻居服务：CRUD 与分页查询。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bgp_peer import BGPPeer
from app.schemas.bgp_peer import BGPPeerCreate, BGPPeerUpdate


async def create_bgp_peer(db: AsyncSession, peer_create: BGPPeerCreate) -> BGPPeer:
    """创建 BGP 邻居。

    Args:
        db: 异步数据库会话
        peer_create: BGP 邻居创建数据

    Returns:
        创建后的 BGPPeer 对象

    Raises:
        ValueError: (peer_ip, remote_asn) 组合已存在
    """
    existing = await get_bgp_peer_by_ip_asn(db, peer_create.peer_ip, peer_create.remote_asn)
    if existing is not None:
        raise ValueError(
            f"BGP 邻居 (peer_ip={peer_create.peer_ip}, remote_asn={peer_create.remote_asn}) 已存在"
        )

    peer = BGPPeer(
        peer_ip=peer_create.peer_ip,
        remote_asn=peer_create.remote_asn,
        address_family=peer_create.address_family,
        session_type=peer_create.session_type,
        routing_policy=peer_create.routing_policy,
        max_prefixes=peer_create.max_prefixes,
        router_id=peer_create.router_id,
        description=peer_create.description,
    )
    db.add(peer)
    await db.flush()
    await db.commit()
    await db.refresh(peer)
    return peer


async def get_bgp_peer(db: AsyncSession, peer_id: int) -> BGPPeer | None:
    """根据 ID 获取 BGP 邻居。"""
    stmt = select(BGPPeer).where(BGPPeer.id == peer_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_bgp_peer_by_ip_asn(db: AsyncSession, peer_ip: str, remote_asn: int) -> BGPPeer | None:
    """按 (peer_ip, remote_asn) 唯一组合查询。"""
    stmt = select(BGPPeer).where(
        BGPPeer.peer_ip == peer_ip,
        BGPPeer.remote_asn == remote_asn,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_bgp_peers(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[BGPPeer]:
    """分页查询 BGP 邻居。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``peer_ip``、``remote_asn``、
            ``address_family``、``session_type``、``session_state``、``router_id``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        BGP 邻居列表
    """
    stmt = select(BGPPeer)
    if filters:
        if filters.get("peer_ip"):
            stmt = stmt.where(BGPPeer.peer_ip == filters["peer_ip"])
        if filters.get("remote_asn") is not None:
            stmt = stmt.where(BGPPeer.remote_asn == filters["remote_asn"])
        if filters.get("address_family"):
            stmt = stmt.where(BGPPeer.address_family == filters["address_family"])
        if filters.get("session_type"):
            stmt = stmt.where(BGPPeer.session_type == filters["session_type"])
        if filters.get("session_state"):
            stmt = stmt.where(BGPPeer.session_state == filters["session_state"])
        if filters.get("router_id") is not None:
            stmt = stmt.where(BGPPeer.router_id == filters["router_id"])

    stmt = stmt.order_by(BGPPeer.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_bgp_peers(db: AsyncSession, filters: dict[str, Any] | None = None) -> int:
    """统计 BGP 邻居数量。"""
    stmt = select(func.count(BGPPeer.id))
    if filters:
        if filters.get("peer_ip"):
            stmt = stmt.where(BGPPeer.peer_ip == filters["peer_ip"])
        if filters.get("remote_asn") is not None:
            stmt = stmt.where(BGPPeer.remote_asn == filters["remote_asn"])
        if filters.get("address_family"):
            stmt = stmt.where(BGPPeer.address_family == filters["address_family"])
        if filters.get("session_type"):
            stmt = stmt.where(BGPPeer.session_type == filters["session_type"])
        if filters.get("session_state"):
            stmt = stmt.where(BGPPeer.session_state == filters["session_state"])
        if filters.get("router_id") is not None:
            stmt = stmt.where(BGPPeer.router_id == filters["router_id"])

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_bgp_peer(db: AsyncSession, peer: BGPPeer, peer_update: BGPPeerUpdate) -> BGPPeer:
    """更新 BGP 邻居。

    Args:
        db: 异步数据库会话
        peer: 待更新的 BGPPeer 对象
        peer_update: 更新数据

    Returns:
        更新后的 BGPPeer 对象

    Raises:
        ValueError: 新 (peer_ip, remote_asn) 组合已存在
    """
    update_data = peer_update.model_dump(exclude_unset=True)

    # 若更新了 peer_ip 或 remote_asn，需重新校验唯一性
    new_ip = update_data.get("peer_ip", peer.peer_ip)
    new_asn = update_data.get("remote_asn", peer.remote_asn)
    if new_ip != peer.peer_ip or new_asn != peer.remote_asn:
        existing = await get_bgp_peer_by_ip_asn(db, new_ip, new_asn)
        if existing is not None and existing.id != peer.id:
            raise ValueError(f"BGP 邻居 (peer_ip={new_ip}, remote_asn={new_asn}) 已存在")

    for field, value in update_data.items():
        setattr(peer, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(peer)
    return peer


async def delete_bgp_peer(db: AsyncSession, peer: BGPPeer) -> None:
    """删除 BGP 邻居。"""
    await db.delete(peer)
    await db.commit()


__all__ = [
    "count_bgp_peers",
    "create_bgp_peer",
    "delete_bgp_peer",
    "get_bgp_peer",
    "get_bgp_peer_by_ip_asn",
    "get_bgp_peers",
    "update_bgp_peer",
]
