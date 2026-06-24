"""事件推送与外部集成数据模型。

包含集成配置、事件订阅、事件投递与外部数据缓存四类核心模型，支撑
RPKI 平台向外部系统（Webhook、Syslog、Kafka、SIEM、IPAM、NMS、RIR、
协作平台等）推送事件并缓存外部数据。
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

from app.core.field_encryption import EncryptedJSON
from app.models.base import Base, TenantMixin, TimestampMixin

# ──────────────────────────────────────────────
# 集成配置
# ──────────────────────────────────────────────


class IntegrationConfig(Base, TimestampMixin, TenantMixin):
    """集成配置模型。

    描述一个外部系统的连接信息与认证凭据，可被多个事件订阅复用。
    支持的集成类型包括：webhook、syslog、kafka、ipam、siem、nms、
    rir、collaboration 等。
    """

    __tablename__ = "integration_configs"
    __table_args__ = (
        Index("ix_integration_configs_type", "integration_type"),
        Index("ix_integration_configs_enabled", "enabled"),
        Index("ix_integration_configs_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="集成名称")
    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="集成唯一编码，用于幂等校验",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="集成描述")
    integration_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=("集成类型：webhook/syslog/kafka/ipam/siem/nms/rir/collaboration"),
    )
    # 子类型用于区分同类集成的不同实现，如 siem 下的 splunk/qradar
    subtype: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="集成子类型，如 splunk/qradar/servicenow/netbox 等",
    )
    # 连接参数（URL、端口、主题等非敏感配置）
    connection_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="连接参数（非敏感）"
    )
    # 认证信息（敏感字段，使用 EncryptedJSON 自动加密存储）
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(
        EncryptedJSON, nullable=True, comment="认证信息（加密存储）"
    )
    # 自定义请求头、模板等额外配置
    extra_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="额外配置（请求头、模板等）"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    # 最近一次连接测试结果
    last_test_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="最近一次测试状态：success/failed/unknown",
    )
    last_test_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次测试消息"
    )
    last_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次测试时间"
    )

    # 关联订阅
    subscriptions: Mapped[list[EventSubscription]] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<IntegrationConfig(id={self.id}, name={self.name}, type={self.integration_type})>"


# ──────────────────────────────────────────────
# 事件订阅
# ──────────────────────────────────────────────


class EventSubscription(Base, TimestampMixin, TenantMixin):
    """事件订阅模型。

    描述一条事件订阅规则：订阅哪些事件类型、过滤条件、目标集成配置、
    投递通道与重试策略。事件分发服务根据订阅将事件路由到对应通道。
    """

    __tablename__ = "event_subscriptions"
    __table_args__ = (
        Index("ix_event_subscriptions_integration_id", "integration_id"),
        Index("ix_event_subscriptions_event_type", "event_type"),
        Index("ix_event_subscriptions_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="订阅名称")
    integration_id: Mapped[int] = mapped_column(
        ForeignKey("integration_configs.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的集成配置 ID",
    )
    # 事件类型：alert.created、incident.updated、roa.changed 等
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="订阅的事件类型（支持通配符 *）",
    )
    # 过滤条件（severity、prefix、asn 等条件）
    filter_conditions: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="事件过滤条件"
    )
    # 投递目标（覆盖集成配置中的默认目标，如特定 topic、频道）
    target: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="投递目标（覆盖集成默认目标）",
    )
    # 投递通道：webhook/syslog/kafka/email/等，与集成类型对应
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="webhook",
        comment="投递通道类型",
    )
    # 消息模板（覆盖默认模板，支持变量插值）
    message_template: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="消息模板配置"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    # 重试策略
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        comment="最大重试次数",
    )
    retry_interval: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        comment="重试间隔（秒）",
    )
    retry_backoff: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="exponential",
        comment="退避策略：fixed/exponential",
    )
    # 投递成功/失败计数（用于监控）
    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="累计成功投递次数",
    )
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="累计失败投递次数",
    )

    # 关联
    integration: Mapped[IntegrationConfig] = relationship(back_populates="subscriptions")
    deliveries: Mapped[list[EventDelivery]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<EventSubscription(id={self.id}, name={self.name}, event_type={self.event_type})>"


# ──────────────────────────────────────────────
# 事件投递
# ──────────────────────────────────────────────


class EventDelivery(Base, TimestampMixin):
    """事件投递记录模型。

    记录每一次事件投递的完整信息：payload、目标、状态、重试次数、
    响应内容等，用于审计、排查与重试。
    """

    __tablename__ = "event_deliveries"
    __table_args__ = (
        Index("ix_event_deliveries_subscription_id", "subscription_id"),
        Index("ix_event_deliveries_status", "status"),
        Index("ix_event_deliveries_event_type", "event_type"),
        Index("ix_event_deliveries_created_at", "created_at"),
        Index("ix_event_deliveries_next_retry_at", "next_retry_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("event_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的订阅 ID",
    )
    # 事件类型冗余存储，便于查询
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, comment="事件类型")
    # 关联的资源 ID（如 alert_id、incident_id）
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="资源类型")
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="资源 ID")
    # 投递 payload（JSON 序列化后的事件内容）
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="投递 payload"
    )
    # 投递状态：pending/success/failed/retrying/dead_letter
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="投递状态",
    )
    # 已重试次数
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="已重试次数",
    )
    # 最后一次尝试时间
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后尝试时间"
    )
    # 下次重试时间
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="下次重试时间"
    )
    # 响应状态码
    response_status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="响应状态码"
    )
    # 响应内容（截断）
    response_body: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="响应内容（截断）"
    )
    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    # 关联
    subscription: Mapped[EventSubscription] = relationship(back_populates="deliveries")

    def __repr__(self) -> str:
        return f"<EventDelivery(id={self.id}, status={self.status}, event_type={self.event_type})>"


# ──────────────────────────────────────────────
# 集成日志
# ──────────────────────────────────────────────


class IntegrationLog(Base, TimestampMixin, TenantMixin):
    """集成日志模型。

    记录集成配置的入站/出站交互日志，包括请求 payload、响应状态与错误信息，
    用于审计与排查集成连通性问题。
    """

    __tablename__ = "integration_logs"
    __table_args__ = (
        Index("ix_integration_logs_config_id", "config_id"),
        Index("ix_integration_logs_direction", "direction"),
        Index("ix_integration_logs_status", "status"),
        Index("ix_integration_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int | None] = mapped_column(
        ForeignKey("integration_configs.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的集成配置 ID",
    )
    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="交互方向：inbound/outbound",
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="请求/响应 payload"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态：pending/success/failed",
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    def __repr__(self) -> str:
        return (
            f"<IntegrationLog(id={self.id}, config_id={self.config_id}, "
            f"direction={self.direction}, status={self.status})>"
        )


# ──────────────────────────────────────────────
# 外部数据缓存
# ──────────────────────────────────────────────


class ExternalDataCache(Base, TimestampMixin, TenantMixin):
    """外部数据缓存模型。

    缓存从外部系统（RIR、IRR、PeeringDB、IPAM 等）查询的数据，避免
    重复请求并支持离线分析。每条记录由数据源类型与缓存键唯一标识。
    """

    __tablename__ = "external_data_cache"
    __table_args__ = (
        Index("ix_external_data_cache_source", "source_type"),
        Index("ix_external_data_cache_cache_key", "cache_key"),
        Index("ix_external_data_cache_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 数据源类型：rir/irr/peeringdb/ipam/cmdb/siem 等
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="数据源类型：rir/irr/peeringdb/ipam 等",
    )
    # 数据源子类型（如 ripe/apnic/arin/nttcom/radb 等）
    source_subtype: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="数据源子类型（如 ripe/apnic/arin）",
    )
    # 缓存键（如 "asn:13335" 或 "prefix:1.1.1.0/24"）
    cache_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="缓存键")
    # 缓存值（JSON 序列化）
    cache_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="缓存值"
    )
    # 原始响应文本（用于审计或调试）
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原始响应文本")
    # 过期时间
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )
    # 数据来源 URL（便于追溯）
    source_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="数据来源 URL"
    )

    def __repr__(self) -> str:
        return f"<ExternalDataCache(id={self.id}, source={self.source_type}, key={self.cache_key})>"


__all__ = [
    "EventDelivery",
    "EventSubscription",
    "ExternalDataCache",
    "Integration",
    "IntegrationConfig",
    "IntegrationLog",
]


# 兼容别名：Task 24 使用 Integration 作为集成配置模型的简称
Integration = IntegrationConfig
