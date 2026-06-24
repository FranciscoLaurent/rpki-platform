"""审计中间件。

记录所有 API 请求的审计日志，包括请求方法、路径、状态码、
响应时间、客户端标识（用户 ID 或 API Key ID）与请求体摘要。
审计日志写入数据库的 ``audit_logs`` 表。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger("app.middleware.audit")

# 豁免路径（不记录审计日志）
EXEMPT_PATHS = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}

# 请求体记录上限（字节）
MAX_BODY_LOG_SIZE = 2048


class AuditMiddleware(BaseHTTPMiddleware):
    """审计中间件。

    记录所有非豁免路径的 API 请求，包括：
    - 请求方法与路径
    - HTTP 状态码
    - 响应耗时（毫秒）
    - 客户端标识（用户 ID、API Key ID 或 IP）
    - 请求 ID（用于链路追踪）
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Any
    ) -> Response:
        """记录请求审计日志。"""
        path = request.url.path

        # 豁免路径直接放行
        if any(path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)

        # 生成请求 ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.monotonic()

        # 执行请求
        try:
            response = await call_next(request)
        except Exception:
            # 记录异常请求
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "API 请求异常",
                request_id=request_id,
                method=request.method,
                path=path,
                latency_ms=latency_ms,
                client_ip=self._get_client_ip(request),
                error="内部服务器错误",
            )
            raise

        latency_ms = int((time.monotonic() - start) * 1000)

        # 获取主体标识
        principal_id = self._get_principal_id(request)

        # 记录审计日志
        log_method = logger.info
        if response.status_code >= 500:
            log_method = logger.error
        elif response.status_code >= 400:
            log_method = logger.warning

        log_method(
            "API 请求审计",
            request_id=request_id,
            method=request.method,
            path=path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            principal_id=principal_id,
            principal_type=getattr(
                request.state, "principal_type", None
            ),
            client_ip=self._get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:200],
        )

        # 添加请求 ID 到响应头
        response.headers["X-Request-ID"] = request_id

        return response

    def _get_principal_id(self, request: Request) -> str | None:
        """获取请求主体 ID。"""
        # 优先从 request.state 获取已认证的主体
        principal = getattr(request.state, "principal", None)
        if principal is not None:
            principal_id = getattr(principal, "id", None)
            if principal_id is not None:
                return str(principal_id)

        # 检查 API Key
        api_key = getattr(request.state, "api_key", None)
        if api_key is not None:
            return f"apikey:{getattr(api_key, 'id', '?')}"

        return None

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端 IP。"""
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "unknown"


__all__ = ["AuditMiddleware"]
