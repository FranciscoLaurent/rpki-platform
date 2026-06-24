"""事件推送通道包。

提供 Webhook、Syslog、Kafka 等事件投递通道的统一抽象与实现。
所有通道继承 ``BaseChannel``，实现 ``send`` 方法。
"""

from __future__ import annotations

from app.services.event_channels.base import BaseChannel, ChannelResult
from app.services.event_channels.kafka_channel import KafkaChannel
from app.services.event_channels.syslog_channel import SyslogChannel
from app.services.event_channels.webhook_channel import WebhookChannel

__all__ = [
    "BaseChannel",
    "ChannelResult",
    "KafkaChannel",
    "SyslogChannel",
    "WebhookChannel",
]
