"""BGP 邻居相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

import ipaddress
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BGPPeerBase(BaseModel):
    """BGP 邻居基础字段。"""

    peer_ip: str = Field(..., description="邻居 IP 地址")
    remote_asn: int = Field(..., ge=1, le=4294967295, description="远端 ASN")
    address_family: str = Field(
        default="ipv4", description="地址族：ipv4/ipv6/dual"
    )
    session_type: str = Field(
        default="ebgp", description="会话类型：ebgp/ibgp"
    )
    routing_policy: str | None = Field(None, description="路由策略描述")
    max_prefixes: int | None = Field(
        None, ge=0, description="最大前缀数"
    )
    router_id: int | None = Field(None, description="关联路由器 ID")
    description: str | None = Field(None, description="描述")

    @field_validator("peer_ip")
    @classmethod
    def validate_peer_ip(cls, v: str) -> str:
        """校验 IP 地址格式。"""
        try:
            ipaddress.ip_address(v)
        except ValueError as e:
            raise ValueError(f"无效的 IP 地址: {e}") from e
        return v

    @field_validator("address_family")
    @classmethod
    def validate_address_family(cls, v: str) -> str:
        """校验地址族取值。"""
        allowed = {"ipv4", "ipv6", "dual"}
        if v not in allowed:
            raise ValueError(f"address_family 必须为 {allowed} 之一")
        return v

    @field_validator("session_type")
    @classmethod
    def validate_session_type(cls, v: str) -> str:
        """校验会话类型取值。"""
        allowed = {"ebgp", "ibgp"}
        if v not in allowed:
            raise ValueError(f"session_type 必须为 {allowed} 之一")
        return v


class BGPPeerCreate(BGPPeerBase):
    """创建 BGP 邻居请求。"""


class BGPPeerUpdate(BaseModel):
    """更新 BGP 邻居请求，所有字段可选。"""

    peer_ip: str | None = Field(None, description="邻居 IP 地址")
    remote_asn: int | None = Field(None, ge=1, le=4294967295, description="远端 ASN")
    address_family: str | None = Field(None, description="地址族")
    session_type: str | None = Field(None, description="会话类型")
    routing_policy: str | None = Field(None, description="路由策略描述")
    max_prefixes: int | None = Field(None, ge=0, description="最大前缀数")
    session_state: str | None = Field(None, description="会话状态")
    router_id: int | None = Field(None, description="关联路由器 ID")
    description: str | None = Field(None, description="描述")

    @field_validator("peer_ip")
    @classmethod
    def validate_peer_ip(cls, v: str | None) -> str | None:
        """校验 IP 地址格式。"""
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
        except ValueError as e:
            raise ValueError(f"无效的 IP 地址: {e}") from e
        return v

    @field_validator("address_family")
    @classmethod
    def validate_address_family(cls, v: str | None) -> str | None:
        """校验地址族取值。"""
        if v is None:
            return v
        allowed = {"ipv4", "ipv6", "dual"}
        if v not in allowed:
            raise ValueError(f"address_family 必须为 {allowed} 之一")
        return v

    @field_validator("session_type")
    @classmethod
    def validate_session_type(cls, v: str | None) -> str | None:
        """校验会话类型取值。"""
        if v is None:
            return v
        allowed = {"ebgp", "ibgp"}
        if v not in allowed:
            raise ValueError(f"session_type 必须为 {allowed} 之一")
        return v

    @field_validator("session_state")
    @classmethod
    def validate_session_state(cls, v: str | None) -> str | None:
        """校验会话状态取值。"""
        if v is None:
            return v
        allowed = {"established", "idle", "active", "connect"}
        if v not in allowed:
            raise ValueError(f"session_state 必须为 {allowed} 之一")
        return v


class BGPPeerResponse(BaseModel):
    """BGP 邻居响应。"""

    id: int
    peer_ip: str
    remote_asn: int
    address_family: str
    session_type: str
    routing_policy: str | None
    max_prefixes: int | None
    session_state: str
    router_id: int | None
    description: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BGPPeerListResponse(BaseModel):
    """BGP 邻居列表响应（带分页信息）。"""

    items: list[BGPPeerResponse]
    total: int
    skip: int
    limit: int


__all__ = [
    "BGPPeerBase",
    "BGPPeerCreate",
    "BGPPeerListResponse",
    "BGPPeerResponse",
    "BGPPeerUpdate",
]
