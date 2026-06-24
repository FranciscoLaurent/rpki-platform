"""事件推送通道基类。

定义所有通道共享的接口与结果类型。
"""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel, Field


class ChannelResult(BaseModel):
    """通道投递结果。"""

    success: bool = Field(..., description="是否成功")
    status_code: int | None = Field(None, description="响应状态码")
    response_body: str | None = Field(None, description="响应内容（截断）")
    error_message: str | None = Field(None, description="错误信息")
    latency_ms: int | None = Field(None, description="延迟（毫秒）")


class BaseChannel(abc.ABC):
    """事件推送通道抽象基类。

    所有具体通道（Webhook、Syslog、Kafka 等）需继承此类并实现 ``send``
    方法。通道是无状态的，每次投递时由调用方传入连接参数与 payload。
    """

    @abc.abstractmethod
    async def send(
        self,
        target: str,
        payload: dict[str, Any],
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """发送事件到目标。

        Args:
            target: 投递目标（URL、topic、host:port 等）
            payload: 事件内容
            connection_params: 连接参数
            auth_config: 认证信息
            extra_config: 额外配置（请求头、模板等）

        Returns:
            投递结果
        """
        ...

    async def test_connection(
        self,
        target: str,
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """测试连接是否可用。

        默认实现发送一个测试 payload，子类可覆盖以提供更轻量的探活逻辑。

        Args:
            target: 投递目标
            connection_params: 连接参数
            auth_config: 认证信息
            extra_config: 额外配置

        Returns:
            测试结果
        """
        return await self.send(
            target=target,
            payload={"event_type": "test", "message": "connection test"},
            connection_params=connection_params,
            auth_config=auth_config,
            extra_config=extra_config,
        )
