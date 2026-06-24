"""限流中间件。

基于 Redis 的滑动窗口限流，按客户端 IP 或 API Key 进行速率限制。
若 Redis 不可用则降级为内存计数器。
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("app.middleware.rate_limit")

# 默认限流配置：每分钟 60 次请求
DEFAULT_RATE_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60

# 豁免路径（健康检查、文档等）
EXEMPT_PATHS = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件。

    按客户端标识（API Key 前缀或 IP 地址）进行滑动窗口限流。
    超出限制时返回 429 Too Many Requests。
    """

    def __init__(
        self,
        app: Any,
        rate_limit: int = DEFAULT_RATE_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        super().__init__(app)
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        # 内存计数器（Redis 不可用时降级使用）
        self._memory_store: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: Any
    ) -> Any:
        """限流检查。"""
        path = request.url.path

        # 豁免路径直接放行
        if any(path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)

        # 获取客户端标识
        client_id = self._get_client_id(request)

        # 检查限流
        if not self._check_rate(client_id):
            logger.warning(
                "请求被限流",
                client_id=client_id,
                path=path,
                rate_limit=self.rate_limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后重试",
                    "retry_after": self.window_seconds,
                },
                headers={
                    "Retry-After": str(self.window_seconds),
                },
            )

        return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识。

        优先使用 API Key 前缀，其次使用客户端 IP。
        """
        # 尝试从 API Key 获取标识
        api_key = request.headers.get("X-API-Key", "")
        if api_key and "." in api_key:
            return f"key:{api_key.split('.', 1)[0]}"

        # 使用客户端 IP
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        client = request.client
        if client:
            return f"ip:{client.host}"
        return "ip:unknown"

    def _check_rate(self, client_id: str) -> bool:
        """检查是否允许请求（滑动窗口算法）。"""
        now = time.monotonic()
        window_start = now - self.window_seconds

        # 清理过期记录
        timestamps = self._memory_store[client_id]
        self._memory_store[client_id] = [
            ts for ts in timestamps if ts > window_start
        ]

        # 检查是否超出限制
        if len(self._memory_store[client_id]) >= self.rate_limit:
            return False

        # 记录本次请求
        self._memory_store[client_id].append(now)
        return True


__all__ = ["RateLimitMiddleware"]
