"""业务服务、客户与路由器模型。

这些模型作为 IPAM/CMDB 资产基线，与前缀、ASN、BGP 邻居关联，
支撑资产一致性检查与关系视图查询。
"""

from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class BusinessService(Base, TimestampMixin, TenantMixin):
    """业务服务模型。

    表示网络所承载的业务系统，用于前缀与业务归属关联分析。
    """

    __tablename__ = "business_services"
    __table_args__ = (
        Index("ix_business_services_name", "name"),
        Index("ix_business_services_importance", "importance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="业务服务名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="业务描述")
    importance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        comment="重要度：critical/important/normal/low",
    )
    owner_contact: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="业务负责人联系方式"
    )

    def __repr__(self) -> str:
        return f"<BusinessService(id={self.id}, name={self.name})>"


class Customer(Base, TimestampMixin, TenantMixin):
    """客户模型。

    记录使用本网络服务的客户信息，与前缀、ASN 关联用于客户资产管理。
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_name", "name"),
        Index("ix_customers_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="客户名称")
    contact_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="客户联系人姓名"
    )
    contact_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="客户联系人邮箱"
    )
    contract_id: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="合同编号")
    service_level: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="standard",
        comment="服务等级：standard/silver/gold/platinum",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/inactive",
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name={self.name})>"


class Router(Base, TimestampMixin, TenantMixin):
    """路由器模型。

    记录网络中路由器设备的元信息，与 BGP 邻居关联用于会话管理。
    """

    __tablename__ = "routers"
    __table_args__ = (
        Index("ix_routers_hostname", "hostname"),
        Index("ix_routers_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, comment="主机名")
    vendor: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="厂商")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="设备型号")
    management_ip: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="管理 IP 地址"
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="部署位置")
    snmp_community: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="SNMP community 字符串"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="状态：active/inactive/maintenance",
    )

    def __repr__(self) -> str:
        return f"<Router(id={self.id}, hostname={self.hostname})>"
