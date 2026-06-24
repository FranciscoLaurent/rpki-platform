"""事件推送与外部集成相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ──────────────────────────────────────────────
# 集成配置
# ──────────────────────────────────────────────


# 集成类型枚举
INTEGRATION_TYPES = {
    "webhook",
    "syslog",
    "kafka",
    "ipam",
    "siem",
    "nms",
    "rir",
    "collaboration",
}

# 投递通道枚举
CHANNEL_TYPES = {
    "webhook",
    "syslog",
    "kafka",
    "email",
    "sms",
    "voice",
    "wechat_work",
    "dingtalk",
    "slack",
    "teams",
    "pagerduty",
}

# 投递状态枚举
DELIVERY_STATUSES = {
    "pending",
    "success",
    "failed",
    "retrying",
    "dead_letter",
}


class IntegrationConfigBase(BaseModel):
    """集成配置基础模式。"""

    name: str = Field(..., max_length=255, description="集成名称")
    code: str = Field(..., max_length=100, description="集成唯一编码")
    description: str | None = Field(None, description="集成描述")
    integration_type: str = Field(..., description="集成类型")
    subtype: str | None = Field(None, description="集成子类型")
    connection_params: dict[str, Any] | None = Field(
        None, description="连接参数（非敏感）"
    )
    auth_config: dict[str, Any] | None = Field(
        None, description="认证信息（加密存储占位）"
    )
    extra_config: dict[str, Any] | None = Field(
        None, description="额外配置"
    )
    enabled: bool = Field(default=True, description="是否启用")

    @field_validator("integration_type")
    @classmethod
    def validate_integration_type(cls, v: str) -> str:
        """校验集成类型。"""
        if v not in INTEGRATION_TYPES:
            raise ValueError(f"集成类型必须是 {INTEGRATION_TYPES} 之一")
        return v


class IntegrationConfigCreate(IntegrationConfigBase):
    """创建集成配置请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class IntegrationConfigUpdate(BaseModel):
    """更新集成配置请求。"""

    name: str | None = Field(None, max_length=255, description="集成名称")
    description: str | None = Field(None, description="集成描述")
    integration_type: str | None = Field(None, description="集成类型")
    subtype: str | None = Field(None, description="集成子类型")
    connection_params: dict[str, Any] | None = Field(
        None, description="连接参数"
    )
    auth_config: dict[str, Any] | None = Field(
        None, description="认证信息"
    )
    extra_config: dict[str, Any] | None = Field(
        None, description="额外配置"
    )
    enabled: bool | None = Field(None, description="是否启用")

    @field_validator("integration_type")
    @classmethod
    def validate_integration_type(cls, v: str | None) -> str | None:
        """校验集成类型。"""
        if v is None:
            return v
        if v not in INTEGRATION_TYPES:
            raise ValueError(f"集成类型必须是 {INTEGRATION_TYPES} 之一")
        return v


class IntegrationConfigResponse(IntegrationConfigBase):
    """集成配置响应。"""

    id: int
    last_test_status: str | None
    last_test_message: str | None
    last_test_at: datetime | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationConfigListResponse(BaseModel):
    """集成配置列表响应。"""

    items: list[IntegrationConfigResponse] = Field(
        default_factory=list, description="集成配置列表"
    )
    total: int = Field(default=0, description="总记录数")


# 兼容别名：Task 24 使用 IntegrationResponse 作为集成配置响应的简称
IntegrationResponse = IntegrationConfigResponse


class IntegrationTestRequest(BaseModel):
    """集成连接测试请求。"""

    # 可选覆盖配置参数，便于在保存前测试
    connection_params: dict[str, Any] | None = Field(
        None, description="覆盖连接参数（可选）"
    )
    auth_config: dict[str, Any] | None = Field(
        None, description="覆盖认证信息（可选）"
    )


class IntegrationTestResult(BaseModel):
    """集成连接测试结果。"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="结果消息")
    latency_ms: int | None = Field(None, description="响应延迟（毫秒）")
    details: dict[str, Any] | None = Field(None, description="详细信息")


# ──────────────────────────────────────────────
# 各集成类型的具体配置 Schema
# ──────────────────────────────────────────────


class WebhookConfig(BaseModel):
    """Webhook 集成配置。"""

    url: str = Field(..., description="Webhook 目标 URL")
    secret: str | None = Field(None, description="HMAC 签名密钥")
    sign_algorithm: str = Field(
        default="sha256", description="HMAC 算法：sha256/sha1/sha512"
    )
    sign_field: str = Field(
        default="X-Signature", description="签名字段名"
    )
    headers: dict[str, str] | None = Field(
        None, description="自定义请求头"
    )
    timeout: int = Field(default=10, description="超时（秒）")
    verify_tls: bool = Field(default=True, description="是否校验 TLS")


class SyslogConfig(BaseModel):
    """Syslog 集成配置。"""

    host: str = Field(..., description="Syslog 服务器地址")
    port: int = Field(default=514, description="Syslog 端口")
    protocol: str = Field(
        default="udp", description="协议：udp/tcp"
    )
    facility: int = Field(default=16, description="Syslog facility")
    severity: int = Field(default=6, description="Syslog severity")
    app_name: str = Field(
        default="rpki-platform", description="应用名"
    )


class KafkaConfig(BaseModel):
    """Kafka 集成配置。"""

    bootstrap_servers: str = Field(
        ..., description="Kafka bootstrap servers"
    )
    topic: str = Field(..., description="目标主题")
    acks: str = Field(default="all", description="确认级别")
    retries: int = Field(default=3, description="重试次数")


class NetBoxConfig(BaseModel):
    """NetBox/IPAM 集成配置。"""

    base_url: str = Field(..., description="NetBox 基础 URL")
    token: str = Field(..., description="API Token")
    verify_tls: bool = Field(default=True, description="是否校验 TLS")
    timeout: int = Field(default=30, description="超时（秒）")


class PrometheusConfig(BaseModel):
    """Prometheus 指标集成配置。"""

    pushgateway_url: str | None = Field(
        None, description="Pushgateway URL（可选，用于推送模式）"
    )
    job_name: str = Field(
        default="rpki-platform", description="任务名"
    )
    instance_label: str | None = Field(
        None, description="实例标签"
    )


class PeeringDBConfig(BaseModel):
    """PeeringDB 集成配置。"""

    api_base: str = Field(
        default="https://www.peeringdb.com/api",
        description="PeeringDB API 基础 URL",
    )
    api_key: str | None = Field(None, description="API Key（可选）")
    timeout: int = Field(default=15, description="超时（秒）")


class NotificationConfig(BaseModel):
    """通知集成通用配置。"""

    # 邮件
    smtp_host: str | None = Field(None, description="SMTP 服务器")
    smtp_port: int = Field(default=587, description="SMTP 端口")
    smtp_username: str | None = Field(None, description="SMTP 用户名")
    smtp_password: str | None = Field(None, description="SMTP 密码")
    smtp_use_tls: bool = Field(default=True, description="是否启用 TLS")
    mail_from: str | None = Field(None, description="发件人地址")
    # 短信/电话
    sms_provider: str | None = Field(
        None, description="短信服务商：aliyun/tencent/twilio"
    )
    sms_api_key: str | None = Field(None, description="短信 API Key")
    sms_api_secret: str | None = Field(
        None, description="短信 API Secret"
    )
    voice_provider: str | None = Field(
        None, description="电话服务商：aliyun/twilio"
    )
    # 企业微信
    wechat_work_webhook: str | None = Field(
        None, description="企业微信机器人 Webhook URL"
    )
    # 钉钉
    dingtalk_webhook: str | None = Field(
        None, description="钉钉机器人 Webhook URL"
    )
    dingtalk_secret: str | None = Field(
        None, description="钉钉加签密钥"
    )
    # Slack
    slack_webhook: str | None = Field(
        None, description="Slack Incoming Webhook URL"
    )
    # Microsoft Teams
    teams_webhook: str | None = Field(
        None, description="Teams Workflows Webhook URL"
    )
    # PagerDuty
    pagerduty_integration_key: str | None = Field(
        None, description="PagerDuty Events API v2 Integration Key"
    )


class SIEMConfig(BaseModel):
    """SIEM/SOC 集成配置。"""

    siem_type: str = Field(
        ..., description="SIEM 类型：splunk/elastic/qradar"
    )
    hec_url: str | None = Field(
        None, description="Splunk HEC URL"
    )
    hec_token: str | None = Field(
        None, description="Splunk HEC Token"
    )
    elastic_url: str | None = Field(
        None, description="Elasticsearch URL"
    )
    elastic_index: str | None = Field(
        None, description="Elasticsearch 索引名"
    )
    timeout: int = Field(default=15, description="超时（秒）")


class ITSMConfig(BaseModel):
    """ITSM 工单系统集成配置。"""

    itsm_type: str = Field(
        ..., description="ITSM 类型：servicenow/jira/freshservice"
    )
    base_url: str = Field(..., description="基础 URL")
    api_token: str | None = Field(None, description="API Token")
    username: str | None = Field(None, description="用户名")
    password: str | None = Field(None, description="密码")
    default_project: str | None = Field(
        None, description="默认项目/工作空间"
    )


class GrafanaConfig(BaseModel):
    """Grafana 集成配置。"""

    base_url: str = Field(..., description="Grafana 基础 URL")
    api_key: str | None = Field(None, description="API Key")
    dashboard_uid: str | None = Field(
        None, description="默认仪表盘 UID"
    )
    timeout: int = Field(default=10, description="超时（秒）")


# ──────────────────────────────────────────────
# 事件订阅
# ──────────────────────────────────────────────


class EventSubscriptionBase(BaseModel):
    """事件订阅基础模式。"""

    name: str = Field(..., max_length=255, description="订阅名称")
    integration_id: int = Field(..., description="关联的集成配置 ID")
    event_type: str = Field(..., description="订阅的事件类型")
    filter_conditions: dict[str, Any] | None = Field(
        None, description="事件过滤条件"
    )
    target: str | None = Field(None, description="投递目标")
    channel: str = Field(default="webhook", description="投递通道类型")
    message_template: dict[str, Any] | None = Field(
        None, description="消息模板配置"
    )
    enabled: bool = Field(default=True, description="是否启用")
    max_retries: int = Field(default=3, ge=0, description="最大重试次数")
    retry_interval: int = Field(
        default=60, ge=1, description="重试间隔（秒）"
    )
    retry_backoff: str = Field(
        default="exponential", description="退避策略：fixed/exponential"
    )

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        """校验投递通道。"""
        if v not in CHANNEL_TYPES:
            raise ValueError(f"投递通道必须是 {CHANNEL_TYPES} 之一")
        return v

    @field_validator("retry_backoff")
    @classmethod
    def validate_retry_backoff(cls, v: str) -> str:
        """校验退避策略。"""
        if v not in {"fixed", "exponential"}:
            raise ValueError("退避策略必须是 fixed 或 exponential")
        return v


class EventSubscriptionCreate(EventSubscriptionBase):
    """创建事件订阅请求。"""

    tenant_id: int | None = Field(None, description="租户 ID")


class EventSubscriptionUpdate(BaseModel):
    """更新事件订阅请求。"""

    name: str | None = Field(None, max_length=255, description="订阅名称")
    event_type: str | None = Field(None, description="订阅的事件类型")
    filter_conditions: dict[str, Any] | None = Field(
        None, description="事件过滤条件"
    )
    target: str | None = Field(None, description="投递目标")
    channel: str | None = Field(None, description="投递通道类型")
    message_template: dict[str, Any] | None = Field(
        None, description="消息模板配置"
    )
    enabled: bool | None = Field(None, description="是否启用")
    max_retries: int | None = Field(None, ge=0, description="最大重试次数")
    retry_interval: int | None = Field(
        None, ge=1, description="重试间隔（秒）"
    )
    retry_backoff: str | None = Field(None, description="退避策略")

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str | None) -> str | None:
        """校验投递通道。"""
        if v is None:
            return v
        if v not in CHANNEL_TYPES:
            raise ValueError(f"投递通道必须是 {CHANNEL_TYPES} 之一")
        return v

    @field_validator("retry_backoff")
    @classmethod
    def validate_retry_backoff(cls, v: str | None) -> str | None:
        """校验退避策略。"""
        if v is None:
            return v
        if v not in {"fixed", "exponential"}:
            raise ValueError("退避策略必须是 fixed 或 exponential")
        return v


class EventSubscriptionResponse(EventSubscriptionBase):
    """事件订阅响应。"""

    id: int
    success_count: int
    failure_count: int
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventSubscriptionQueryParams(BaseModel):
    """事件订阅查询参数。"""

    integration_id: int | None = Field(None, description="按集成配置过滤")
    event_type: str | None = Field(None, description="按事件类型过滤")
    channel: str | None = Field(None, description="按通道过滤")
    enabled: bool | None = Field(None, description="按启用状态过滤")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


# ──────────────────────────────────────────────
# 事件投递
# ──────────────────────────────────────────────


class EventDeliveryResponse(BaseModel):
    """事件投递响应。"""

    id: int
    subscription_id: int
    event_type: str
    resource_type: str | None
    resource_id: str | None
    payload: dict[str, Any] | None
    status: str
    retry_count: int
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    response_status_code: int | None
    response_body: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventDeliveryQueryParams(BaseModel):
    """事件投递查询参数。"""

    subscription_id: int | None = Field(None, description="按订阅过滤")
    event_type: str | None = Field(None, description="按事件类型过滤")
    status: str | None = Field(None, description="按状态过滤")
    resource_type: str | None = Field(None, description="按资源类型过滤")
    resource_id: str | None = Field(None, description="按资源 ID 过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=50, ge=1, le=500, description="返回记录数上限")


class EventDeliveryRetryRequest(BaseModel):
    """事件投递重试请求。"""

    # 是否强制重试（即使状态为 dead_letter）
    force: bool = Field(default=False, description="是否强制重试")


# ──────────────────────────────────────────────
# 集成日志
# ──────────────────────────────────────────────


class IntegrationLogResponse(BaseModel):
    """集成日志响应。"""

    id: int
    config_id: int | None
    direction: str
    payload: dict[str, Any] | None
    status: str
    error: str | None
    tenant_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationLogQueryParams(BaseModel):
    """集成日志查询参数。"""

    config_id: int | None = Field(None, description="按集成配置过滤")
    direction: str | None = Field(
        None, description="按方向过滤：inbound/outbound"
    )
    status: str | None = Field(None, description="按状态过滤")
    start_time: datetime | None = Field(None, description="起始时间")
    end_time: datetime | None = Field(None, description="截止时间")
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(
        default=50, ge=1, le=500, description="返回记录数上限"
    )


# ──────────────────────────────────────────────
# 事件分发
# ──────────────────────────────────────────────


class EventDispatchRequest(BaseModel):
    """事件分发请求。

    用于内部模块（如告警、事件服务）触发事件分发。
    """

    event_type: str = Field(..., description="事件类型")
    resource_type: str | None = Field(None, description="资源类型")
    resource_id: str | None = Field(None, description="资源 ID")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="事件 payload"
    )
    tenant_id: int | None = Field(None, description="租户 ID")


class EventDispatchResult(BaseModel):
    """事件分发结果。"""

    event_type: str = Field(..., description="事件类型")
    matched_subscriptions: int = Field(
        0, description="匹配的订阅数"
    )
    deliveries_created: int = Field(
        0, description="创建的投递记录数"
    )
    delivery_ids: list[int] = Field(
        default_factory=list, description="投递记录 ID 列表"
    )


# ──────────────────────────────────────────────
# 外部数据查询
# ──────────────────────────────────────────────


class ExternalDataQueryParams(BaseModel):
    """外部数据查询参数。"""

    source_type: str = Field(..., description="数据源类型")
    query: str = Field(..., description="查询条件（如 ASN、前缀）")
    use_cache: bool = Field(default=True, description="是否使用缓存")
    refresh: bool = Field(default=False, description="是否强制刷新缓存")


class ExternalDataResponse(BaseModel):
    """外部数据查询响应。"""

    source_type: str = Field(..., description="数据源类型")
    source_subtype: str | None = Field(None, description="数据源子类型")
    query: str = Field(..., description="查询条件")
    data: dict[str, Any] | None = Field(None, description="查询结果")
    cached: bool = Field(False, description="是否来自缓存")
    fetched_at: datetime = Field(..., description="数据获取时间")
    source_url: str | None = Field(None, description="数据来源 URL")


class IRRRecord(BaseModel):
    """IRR 数据库记录。"""

    source: str = Field(..., description="IRR 数据源（如 ripe、radb）")
    route: str = Field(..., description="路由前缀")
    origin_as: str | None = Field(None, description="起源 AS")
    descr: str | None = Field(None, description="描述")
    mnt_by: str | None = Field(None, description="维护者")
    last_modified: str | None = Field(None, description="最后修改时间")


class PeeringDBNetwork(BaseModel):
    """PeeringDB 网络信息。"""

    asn: int = Field(..., description="ASN")
    name: str | None = Field(None, description="网络名称")
    aka: str | None = Field(None, description="别名")
    website: str | None = Field(None, description="网站")
    info_type: str | None = Field(None, description="网络类型")
    info_prefixes4: int | None = Field(None, description="IPv4 前缀数")
    info_prefixes6: int | None = Field(None, description="IPv6 前缀数")
    info_traffic: str | None = Field(None, description="流量级别")
    info_scope: str | None = Field(None, description="覆盖范围")
    country: str | None = Field(None, description="国家")


class RIRAllocation(BaseModel):
    """RIR 分配记录。"""

    rir: str = Field(..., description="RIR 名称（如 ripe、apnic）")
    asn: int | None = Field(None, description="ASN")
    prefix: str | None = Field(None, description="前缀")
    holder: str | None = Field(None, description="持有者")
    country: str | None = Field(None, description="国家")
    status: str | None = Field(None, description="状态")
    allocated_at: str | None = Field(None, description="分配时间")


# ──────────────────────────────────────────────
# 事件推送（Task 24）
# ──────────────────────────────────────────────


class EventPublishRequest(BaseModel):
    """事件推送请求。"""

    event_type: str = Field(..., description="事件类型")
    event_data: dict[str, Any] = Field(
        default_factory=dict, description="事件数据"
    )
    channels: list[str] = Field(
        default_factory=lambda: ["webhook"],
        description="推送通道列表：webhook/syslog/kafka",
    )


class ChannelDeliveryResult(BaseModel):
    """单通道投递结果。"""

    integration_id: int | None = Field(None, description="集成配置 ID")
    integration_name: str | None = Field(None, description="集成名称")
    success: bool = Field(..., description="是否成功")
    latency_ms: int | None = Field(None, description="延迟（毫秒）")


class ChannelPublishResult(BaseModel):
    """单通道推送结果。"""

    success: bool = Field(..., description="通道整体是否成功")
    success_count: int = Field(default=0, description="成功投递数")
    failure_count: int = Field(default=0, description="失败投递数")
    deliveries: list[ChannelDeliveryResult] = Field(
        default_factory=list, description="投递详情"
    )
    message: str | None = Field(None, description="消息")


class EventPublishResult(BaseModel):
    """事件推送结果。"""

    event_type: str = Field(..., description="事件类型")
    channels: dict[str, ChannelPublishResult] = Field(
        default_factory=dict, description="各通道推送结果"
    )
    total_success: int = Field(default=0, description="总成功数")
    total_failure: int = Field(default=0, description="总失败数")


class PushChannelInfo(BaseModel):
    """推送通道信息。"""

    id: int = Field(..., description="集成配置 ID")
    name: str = Field(..., description="集成名称")
    type: str = Field(..., description="通道类型")
    subtype: str | None = Field(None, description="子类型")
    enabled: bool = Field(..., description="是否启用")
    status: str = Field(..., description="最近测试状态")
    last_test_at: datetime | None = Field(None, description="最近测试时间")
    tenant_id: int | None = Field(None, description="租户 ID")


class PushChannelListResponse(BaseModel):
    """推送通道列表响应。"""

    items: list[PushChannelInfo] = Field(
        default_factory=list, description="通道列表"
    )
    total: int = Field(default=0, description="总数")


class ChannelTestRequest(BaseModel):
    """通道测试请求。"""

    channel_type: str = Field(..., description="通道类型：webhook/syslog/kafka")
    config: dict[str, Any] = Field(..., description="通道配置")


class ChannelTestResult(BaseModel):
    """通道测试结果。"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="结果消息")
    latency_ms: int | None = Field(None, description="延迟（毫秒）")


# ──────────────────────────────────────────────
# 外部信息查询（Task 24）
# ──────────────────────────────────────────────


class ExternalInfoQuery(BaseModel):
    """外部信息查询请求。"""

    source: str = Field(
        ..., description="数据源：rir/irr/peeringdb"
    )
    query: str = Field(..., description="查询条件（前缀或 ASN）")
    config: dict[str, Any] = Field(
        default_factory=dict, description="数据源配置（可选）"
    )


class ExternalInfoResult(BaseModel):
    """外部信息查询结果。"""

    source: str = Field(..., description="数据源")
    query: str = Field(..., description="查询条件")
    success: bool = Field(..., description="是否成功")
    data: dict[str, Any] | None = Field(None, description="查询结果")
    cached: bool = Field(default=False, description="是否来自缓存")
    message: str | None = Field(None, description="消息")


class EnrichPrefixRequest(BaseModel):
    """前缀信息丰富请求。"""

    prefix: str = Field(..., description="网络前缀")


class EnrichASNRequest(BaseModel):
    """ASN 信息丰富请求。"""

    asn: int = Field(..., description="AS 号")


class EnrichResult(BaseModel):
    """信息丰富结果。"""

    success: bool = Field(..., description="是否成功")
    data: dict[str, Any] = Field(..., description="丰富后的数据")


# ──────────────────────────────────────────────
# 指标导出与 Grafana（Task 24）
# ──────────────────────────────────────────────


class MetricExport(BaseModel):
    """单个导出指标。"""

    name: str = Field(..., description="指标名称")
    value: float = Field(..., description="指标值")
    labels: dict[str, str] = Field(
        default_factory=dict, description="标签"
    )
    help: str | None = Field(None, description="指标说明")
    type: str = Field(default="gauge", description="指标类型")


class MetricExportResponse(BaseModel):
    """指标导出响应。"""

    metrics: list[MetricExport] = Field(
        default_factory=list, description="指标列表"
    )
    total: int = Field(default=0, description="指标总数")
    exported_at: datetime = Field(..., description="导出时间")


class GrafanaDashboardRequest(BaseModel):
    """Grafana Dashboard 生成请求。"""

    title: str | None = Field(None, description="仪表盘标题")
    uid: str | None = Field(None, description="仪表盘 UID")
    datasource: str | None = Field(None, description="数据源")


class GrafanaDashboard(BaseModel):
    """Grafana Dashboard 配置。"""

    id: int | None = Field(None, description="仪表盘 ID")
    uid: str = Field(..., description="仪表盘 UID")
    title: str = Field(..., description="仪表盘标题")
    tags: list[str] = Field(default_factory=list, description="标签")
    timezone: str = Field(default="browser", description="时区")
    schemaVersion: int = Field(..., description="Schema 版本")
    version: int = Field(default=1, description="版本号")
    refresh: str = Field(default="30s", description="刷新间隔")
    time: dict[str, str] = Field(..., description="时间范围")
    panels: list[dict[str, Any]] = Field(
        default_factory=list, description="面板列表"
    )
    templating: dict[str, Any] | None = Field(
        None, description="模板变量"
    )


__all__ = [
    "CHANNEL_TYPES",
    "ChannelDeliveryResult",
    "ChannelPublishResult",
    "ChannelTestRequest",
    "ChannelTestResult",
    "DELIVERY_STATUSES",
    "EnrichASNRequest",
    "EnrichPrefixRequest",
    "EnrichResult",
    "EventDeliveryQueryParams",
    "EventDeliveryResponse",
    "EventDeliveryRetryRequest",
    "EventDispatchRequest",
    "EventDispatchResult",
    "EventPublishRequest",
    "EventPublishResult",
    "EventSubscriptionBase",
    "EventSubscriptionCreate",
    "EventSubscriptionQueryParams",
    "EventSubscriptionResponse",
    "EventSubscriptionUpdate",
    "ExternalDataQueryParams",
    "ExternalDataResponse",
    "ExternalInfoQuery",
    "ExternalInfoResult",
    "GrafanaDashboard",
    "GrafanaDashboardRequest",
    "INTEGRATION_TYPES",
    "IRRRecord",
    "IntegrationConfigBase",
    "IntegrationConfigCreate",
    "IntegrationConfigListResponse",
    "IntegrationConfigResponse",
    "IntegrationConfigUpdate",
    "IntegrationResponse",
    "IntegrationTestRequest",
    "IntegrationTestResult",
    "MetricExport",
    "MetricExportResponse",
    "PeeringDBNetwork",
    "PushChannelInfo",
    "PushChannelListResponse",
    "RIRAllocation",
]
