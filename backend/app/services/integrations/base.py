"""外部集成适配器基类。

定义所有适配器共享的接口与结果类型。
"""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel, Field


class AdapterResult(BaseModel):
    """适配器操作结果。"""

    success: bool = Field(..., description="是否成功")
    data: dict[str, Any] | None = Field(None, description="返回数据")
    error_message: str | None = Field(None, description="错误信息")
    latency_ms: int | None = Field(None, description="延迟（毫秒）")


class BaseAdapter(abc.ABC):
    """外部集成适配器抽象基类。

    所有具体适配器（IPAM、SIEM、NMS、RIR、协作通知等）需继承此类。
    适配器封装外部系统的 API 调用细节，向上层提供统一接口。
    """

    def __init__(
        self,
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        """初始化适配器。

        Args:
            connection_params: 连接参数（URL、端口等）
            auth_config: 认证信息
            extra_config: 额外配置
        """
        self.connection_params = connection_params or {}
        self.auth_config = auth_config or {}
        self.extra_config = extra_config or {}

    @abc.abstractmethod
    async def test_connection(self) -> AdapterResult:
        """测试与外部系统的连接是否可用。"""
        ...

    def _get_auth_headers(self) -> dict[str, str]:
        """构造认证请求头。

        支持的认证类型：
        - ``bearer``: Bearer Token
        - ``basic``: Basic 认证
        - ``api_key``: API Key（通过 header_name 与 header_value 配置）
        """
        import base64

        headers: dict[str, str] = {}
        auth_type = self.auth_config.get("type")

        if auth_type == "bearer":
            token = self.auth_config.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "basic":
            username = self.auth_config.get("username", "")
            password = self.auth_config.get("password", "")
            credentials = base64.b64encode(
                f"{username}:{password}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = f"Basic {credentials}"
        elif auth_type == "api_key":
            header_name = self.auth_config.get(
                "header_name", "X-API-Key"
            )
            header_value = self.auth_config.get("header_value", "")
            headers[header_name] = header_value

        return headers

    def _get_base_url(self) -> str:
        """获取基础 URL（去除末尾斜杠）。"""
        url = self.connection_params.get("url", "").rstrip("/")
        return url

    def _get_timeout(self) -> float:
        """获取请求超时（秒）。"""
        return float(self.connection_params.get("timeout", 10))
