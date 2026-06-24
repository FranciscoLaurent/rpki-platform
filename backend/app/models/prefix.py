"""IP 前缀模型。

存储 CIDR 表示的 IP 前缀，支持自引用父子关系与 IPv4/IPv6 双栈。
"""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    pass


class Prefix(Base, TimestampMixin, TenantMixin):
    """IP 前缀模型，用于 IPAM 资产管理。

    前缀以 CIDR 字符串形式存储（如 ``192.168.1.0/24``），
    通过 ``ipaddress`` 标准库提供 IPv4/IPv6 判断与包含关系辅助方法。
    """

    __tablename__ = "prefixes"
    __table_args__ = (
        Index("ix_prefixes_family_length", "prefix_family", "prefix_length"),
        Index("ix_prefixes_status", "status"),
        Index("ix_prefixes_parent_id", "parent_id"),
        Index("ix_prefixes_customer_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="CIDR 表示的 IP 前缀，如 192.168.1.0/24",
    )
    prefix_family: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="IP 协议族：4 表示 IPv4，6 表示 IPv6",
    )
    prefix_length: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="前缀长度（掩码位数）"
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("prefixes.id", ondelete="SET NULL"),
        nullable=True,
        comment="父前缀 ID，自引用",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/inactive/reserved/deprecated",
    )
    importance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        comment="重要度：critical/important/normal/low",
    )
    business_service: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="业务归属"
    )
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="地域")
    site: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="机房")
    cloud_zone: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="云区域")
    customer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联客户 ID",
    )
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list, comment="标签列表")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="描述")
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="登记时间"
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )

    # 自引用关系：父前缀与子前缀
    parent: Mapped[Prefix] = relationship(
        "Prefix",
        remote_side="Prefix.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[list[Prefix]] = relationship(
        "Prefix",
        back_populates="parent",
        foreign_keys=[parent_id],
    )

    def __repr__(self) -> str:
        return f"<Prefix(id={self.id}, prefix={self.prefix})>"

    # ──────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────

    def is_ipv4(self) -> bool:
        """判断是否为 IPv4 前缀。"""
        return self.prefix_family == 4

    def is_ipv6(self) -> bool:
        """判断是否为 IPv6 前缀。"""
        return self.prefix_family == 6

    def _as_network(self) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
        """将前缀字符串转换为 ipaddress 网络对象。"""
        return ipaddress.ip_network(self.prefix, strict=False)

    def contains(self, other_prefix: str | Prefix) -> bool:
        """判断当前前缀是否包含另一个前缀。

        Args:
            other_prefix: 另一个前缀，可为 CIDR 字符串或 Prefix 对象。

        Returns:
            当前前缀严格包含另一个前缀时返回 True，相等时返回 False。
        """
        other = other_prefix.prefix if isinstance(other_prefix, Prefix) else other_prefix
        try:
            self_net = self._as_network()
            other_net = ipaddress.ip_network(other, strict=False)
        except ValueError:
            return False
        # 严格包含：other 是 self 的真子网
        return other_net != self_net and other_net.subnet_of(self_net)
