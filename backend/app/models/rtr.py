"""RPKI-RTR 服务与设备集成数据模型。

包含 RTR 服务实例、客户端会话、序列号历史与设备配置模板四类模型，
支撑 RPKI-RTR 协议（RFC 8210）服务端能力与多厂商设备配置下发。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin


# ──────────────────────────────────────────────
# RTR 服务实例
# ──────────────────────────────────────────────


class RTRServer(Base, TimestampMixin, TenantMixin):
    """RTR 服务实例模型。

    表示一个 RPKI-RTR 协议（RFC 8210）服务端实例，监听指定端口
    向路由器等客户端推送 VRP 数据。支持 mTLS 与白名单访问控制。
    """

    __tablename__ = "rtr_servers"
    __table_args__ = (
        Index("ix_rtr_servers_status", "status"),
        Index("ix_rtr_servers_listen_host_port", "listen_host", "listen_port"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="RTR 服务名称"
    )
    listen_host: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="0.0.0.0",
        comment="监听地址",
    )
    listen_port: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8282, comment="监听端口"
    )
    session_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="RTR Session ID，缓存重启后需变更",
    )
    current_serial: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前序列号，每次 VRP 更新递增",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="stopped",
        comment="服务状态：running/stopped/error",
    )
    vrps_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="当前 VRP 数量"
    )
    connected_clients: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前连接客户端数",
    )
    mtls_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否启用 mTLS 双向认证",
    )
    whitelist: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="允许连接的客户端 IP 列表（空表示不限制）",
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="其他配置（如刷新间隔、超时等）"
    )
    last_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次启动时间"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次错误信息"
    )

    # 关联
    sessions: Mapped[list[RTRSession]] = relationship(
        back_populates="server",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    serial_histories: Mapped[list[RTRSerialHistory]] = relationship(
        back_populates="server",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RTRServer(id={self.id}, name={self.name}, "
            f"port={self.listen_port}, status={self.status})>"
        )


# ──────────────────────────────────────────────
# RTR 客户端会话
# ──────────────────────────────────────────────


class RTRSession(Base, TimestampMixin):
    """RTR 客户端会话模型。

    记录一个 RTR 客户端（路由器）与服务端的会话信息，包括客户端
    协议版本、同步进度与流量统计。
    """

    __tablename__ = "rtr_sessions"
    __table_args__ = (
        Index("ix_rtr_sessions_server_id", "server_id"),
        Index("ix_rtr_sessions_client_ip", "client_ip"),
        Index("ix_rtr_sessions_session_state", "session_state"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    server_id: Mapped[int] = mapped_column(
        ForeignKey("rtr_servers.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 RTR 服务 ID",
    )
    client_ip: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="客户端 IP 地址"
    )
    client_port: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="客户端端口"
    )
    client_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="RTR 协议版本：0 或 1"
    )
    session_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="idle",
        comment="会话状态：established/syncing/idle/error",
    )
    last_serial: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="客户端最后同步的序列号",
    )
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="连接建立时间"
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近活动时间"
    )
    bytes_sent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已发送字节数"
    )
    bytes_received: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已接收字节数"
    )

    # 关联
    server: Mapped[RTRServer] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        return (
            f"<RTRSession(id={self.id}, server_id={self.server_id}, "
            f"client_ip={self.client_ip}, state={self.session_state})>"
        )


# ──────────────────────────────────────────────
# 序列号历史
# ──────────────────────────────────────────────


class RTRSerialHistory(Base, TimestampMixin):
    """RTR 序列号历史模型。

    记录 RTR 服务每次序列号变更的详情，包括变更类型、VRP 增删改数量
    与关联快照，用于审计与回滚。
    """

    __tablename__ = "rtr_serial_history"
    __table_args__ = (
        Index("ix_rtr_serial_history_server_id", "server_id"),
        Index("ix_rtr_serial_history_serial_number", "serial_number"),
        Index("ix_rtr_serial_history_change_type", "change_type"),
        Index("ix_rtr_serial_history_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    server_id: Mapped[int] = mapped_column(
        ForeignKey("rtr_servers.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 RTR 服务 ID",
    )
    serial_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="序列号"
    )
    change_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="变更类型：full_update/incremental_update/rollback",
    )
    vrps_added: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="新增 VRP 数量"
    )
    vrps_removed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="移除 VRP 数量"
    )
    vrps_modified: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="修改 VRP 数量"
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="关联的 RPKI 快照 ID",
    )
    note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )

    # 关联
    server: Mapped[RTRServer] = relationship(
        back_populates="serial_histories"
    )

    def __repr__(self) -> str:
        return (
            f"<RTRSerialHistory(id={self.id}, server_id={self.server_id}, "
            f"serial={self.serial_number}, type={self.change_type})>"
        )


# ──────────────────────────────────────────────
# 设备配置模板
# ──────────────────────────────────────────────


class DeviceConfigTemplate(Base, TimestampMixin, TenantMixin):
    """设备配置模板模型。

    存储各厂商路由器的 RPKI/RTR 客户端配置模板，模板内容含变量占位符
    （如 ``{{ asn }}``、``{{ rtr_server }}``），生成时按变量字典填充。
    """

    __tablename__ = "device_config_templates"
    __table_args__ = (
        Index("ix_device_config_templates_vendor", "vendor"),
        Index("ix_device_config_templates_template_type", "template_type"),
        Index("ix_device_config_templates_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="模板名称"
    )
    vendor: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "厂商：cisco_ios_xe/cisco_ios_xr/juniper_junos/huawei_vrp/"
            "h3c/arista_eos/nokia_sros/frr/bird/openbgpd"
        ),
    )
    template_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment=(
            "模板类型：rtr_client/rov_policy/rollback/risk_notice"
        ),
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="模板内容，含变量占位符（如 {{ asn }}）",
    )
    variables: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="变量定义（变量名、描述、是否必填、默认值等）",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="模板描述"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceConfigTemplate(id={self.id}, name={self.name}, "
            f"vendor={self.vendor}, type={self.template_type})>"
        )


__all__ = [
    "DeviceConfigTemplate",
    "RTRServer",
    "RTRSession",
    "RTRSerialHistory",
]
