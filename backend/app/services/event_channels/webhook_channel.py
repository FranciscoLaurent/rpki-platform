"""Webhook 推送通道。

通过 HTTP POST 将事件推送到外部 Webhook 端点，支持 HMAC 签名、
自定义请求头、超时与重试。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services.event_channels.base import BaseChannel, ChannelResult

logger: BoundLogger = get_logger("app.event_channels.webhook")


class WebhookChannel(BaseChannel):
    """Webhook 推送通道。

    支持以下连接参数：
    - ``timeout``: 请求超时（秒，默认 10）
    - ``verify_tls``: 是否校验 TLS（默认 True）

    支持以下认证配置：
    - ``type``: 认证类型（``hmac``、``bearer``、``basic``、``header``）
    - ``secret``: HMAC 密钥（type=hmac 时）
    - ``token``: Bearer Token（type=bearer 时）
    - ``username``/``password``: Basic 认证（type=basic 时）
    - ``header_name``/``header_value``: 自定义请求头（type=header 时）

    支持以下额外配置：
    - ``headers``: 自定义请求头字典
    - ``sign_field``: HMAC 签名字段名（默认 ``X-Signature``）
    - ``sign_algorithm``: HMAC 算法（默认 sha256）
    """

    async def send(
        self,
        target: str,
        payload: dict[str, Any],
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """发送事件到 Webhook 端点。"""
        connection_params = connection_params or {}
        auth_config = auth_config or {}
        extra_config = extra_config or {}

        timeout = float(connection_params.get("timeout", 10))
        verify_tls = connection_params.get("verify_tls", True)

        # 序列化 payload
        body = json.dumps(payload, ensure_ascii=False, default=str).encode(
            "utf-8"
        )

        # 构造请求头
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RPKI-Platform/1.0",
        }
        custom_headers = extra_config.get("headers") or {}
        headers.update(custom_headers)

        # 处理认证
        self._apply_auth(headers, body, auth_config, extra_config)

        start = time.monotonic()
        try:
            # TODO: 实际生产环境应使用连接池与重试策略
            async with httpx.AsyncClient(
                timeout=timeout, verify=verify_tls
            ) as client:
                response = await client.post(
                    target, content=body, headers=headers
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            response_body = response.text
            if len(response_body) > 2000:
                response_body = response_body[:2000] + "...[truncated]"

            success = 200 <= response.status_code < 300
            if not success:
                logger.warning(
                    "Webhook 推送返回非 2xx 状态码",
                    target=target,
                    status_code=response.status_code,
                )
            else:
                logger.info(
                    "Webhook 推送成功",
                    target=target,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                )

            return ChannelResult(
                success=success,
                status_code=response.status_code,
                response_body=response_body,
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Webhook 推送超时", target=target, error=str(e)
            )
            return ChannelResult(
                success=False,
                error_message=f"请求超时: {e}",
                latency_ms=latency_ms,
            )
        except httpx.HTTPError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Webhook 推送失败", target=target, error=str(e)
            )
            return ChannelResult(
                success=False,
                error_message=f"HTTP 错误: {e}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Webhook 推送异常", target=target, error=str(e)
            )
            return ChannelResult(
                success=False,
                error_message=f"未知错误: {e}",
                latency_ms=latency_ms,
            )

    async def test_connection(
        self,
        target: str,
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """测试 Webhook 连接（发送 HEAD 请求）。"""
        connection_params = connection_params or {}
        auth_config = auth_config or {}
        extra_config = extra_config or {}

        timeout = float(connection_params.get("timeout", 5))
        verify_tls = connection_params.get("verify_tls", True)

        headers = {"User-Agent": "RPKI-Platform/1.0"}
        custom_headers = extra_config.get("headers") or {}
        headers.update(custom_headers)
        self._apply_auth(headers, b"", auth_config, extra_config)

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=timeout, verify=verify_tls
            ) as client:
                response = await client.head(target, headers=headers)
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 500
            return ChannelResult(
                success=success,
                status_code=response.status_code,
                latency_ms=latency_ms,
                error_message=None
                if success
                else f"状态码 {response.status_code}",
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return ChannelResult(
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    def _apply_auth(
        self,
        headers: dict[str, str],
        body: bytes,
        auth_config: dict[str, Any],
        extra_config: dict[str, Any],
    ) -> None:
        """应用认证配置到请求头。"""
        auth_type = auth_config.get("type")
        if auth_type is None:
            return

        if auth_type == "hmac":
            secret = auth_config.get("secret", "")
            algorithm = extra_config.get("sign_algorithm", "sha256")
            sign_field = extra_config.get("sign_field", "X-Signature")
            # 计算 HMAC 签名
            digestmod = getattr(hashlib, algorithm, hashlib.sha256)
            signature = hmac.new(
                secret.encode("utf-8"), body, digestmod
            ).hexdigest()
            headers[sign_field] = signature
            headers["X-Signature-Algorithm"] = algorithm
        elif auth_type == "bearer":
            token = auth_config.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "basic":
            import base64

            username = auth_config.get("username", "")
            password = auth_config.get("password", "")
            credentials = base64.b64encode(
                f"{username}:{password}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = f"Basic {credentials}"
        elif auth_type == "header":
            header_name = auth_config.get("header_name", "X-API-Key")
            header_value = auth_config.get("header_value", "")
            headers[header_name] = header_value

    async def _sleep(self, seconds: float) -> None:
        """可被 mock 的 sleep 方法。"""
        await asyncio.sleep(seconds)
