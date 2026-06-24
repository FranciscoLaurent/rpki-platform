"""AS（自治系统）模型。

记录网络中各 AS 的元信息、关系类型与联系人，支撑 BGP 邻居与 ROA 关联分析。
"""

from __future__ import annotations

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class ASN(Base, TimestampMixin, TenantMixin):
    """AS（自治系统）模型。

    记录 AS 号、名称、与本地网络的关系类型（自有/客户/供应商/对等等），
    以及 NOC 联系人与风险画像，用于 BGP 邻居管理与路由策略制定。
    """

    __tablename__ = "asns"
    __table_args__ = (
        Index("ix_asns_asn_type", "asn_type"),
        Index("ix_asns_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    asn: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        comment="AS 号码（32 位无符号整数）",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="AS 名称"
    )
    asn_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="provider",
        comment=(
            "AS 关系类型：own/customer/provider/peer/ixp/route_server/scrubber"
        ),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/inactive",
    )
    risk_profile: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="风险画像描述"
    )
    contact_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="联系人姓名"
    )
    contact_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="联系人邮箱"
    )
    noc_phone: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="NOC 联系电话"
    )
    emergency_contact: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="紧急联系方式"
    )
    relationship_tags: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list, comment="关系标签列表"
    )
    description: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="描述"
    )

    def __repr__(self) -> str:
        return f"<ASN(id={self.id}, asn={self.asn}, name={self.name})>"
