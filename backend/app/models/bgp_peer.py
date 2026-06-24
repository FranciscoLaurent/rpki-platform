"""BGP 邻居模型。

记录与远端 AS 建立的 BGP 会话信息，用于路由策略与最大前缀控制。
"""

from __future__ import annotations

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class BGPPeer(Base, TimestampMixin, TenantMixin):
    """BGP 邻居模型。

    记录与远端 AS 建立的 BGP 会话，包括邻居 IP、远端 ASN、地址族、
    会话类型（eBGP/iBGP）、路由策略与最大前缀数等。
    """

    __tablename__ = "bgp_peers"
    __table_args__ = (
        UniqueConstraint("peer_ip", "remote_asn", name="uq_bgp_peers_peer_ip_remote_asn"),
        Index("ix_bgp_peers_peer_ip", "peer_ip"),
        Index("ix_bgp_peers_remote_asn", "remote_asn"),
        Index("ix_bgp_peers_session_state", "session_state"),
        Index("ix_bgp_peers_router_id", "router_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    peer_ip: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="邻居 IP 地址（IPv4 或 IPv6）",
    )
    remote_asn: Mapped[int] = mapped_column(Integer, nullable=False, comment="远端 ASN")
    address_family: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ipv4",
        comment="地址族：ipv4/ipv6/dual",
    )
    session_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ebgp",
        comment="会话类型：ebgp/ibgp",
    )
    routing_policy: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="路由策略描述"
    )
    max_prefixes: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最大前缀数")
    session_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="idle",
        comment="会话状态：established/idle/active/connect",
    )
    router_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("routers.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联路由器 ID",
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="描述")

    def __repr__(self) -> str:
        return f"<BGPPeer(id={self.id}, peer_ip={self.peer_ip}, remote_asn={self.remote_asn})>"
