"""IP 白名单中间件。

仅允许配置的 IP 白名单中的客户端访问 API。当 ``settings.IP_WHITELIST``
为空时，所有 IP 均允许访问（即不启用白名单限制）。

可通过 ``settings.IP_WHITELIST_ENABLED`` 显式开关，并通过
``settings.IP_WHITELIST_PATHS`` 限定仅对指定路径前缀启用白名单。
"""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.middleware.ip_whitelist")

# 豁免路径（健康检查、文档等）
EXEMPT_PATHS = {
    "/api/v1/health",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """IP 白名单中间件。

    启用条件（满足其一即生效）：
    1. ``settings.IP_WHITELIST_ENABLED`` 为 True；或
    2. ``settings.IP_WHITELIST`` 非空。

    当 ``settings.IP_WHITELIST_PATHS`` 非空时，仅对匹配前缀的路径启用白名单；
    为空时对所有非豁免路径生效。支持 CIDR 表示法（如 ``192.168.1.0/24``）
    与单 IP（如 ``10.0.0.1``）。
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        # 预解析白名单，区分 CIDR 与单 IP
        self._exact_ips: set[str] = set()
        self._networks: list[Any] = []
        self._parse_whitelist(settings.IP_WHITELIST)
        # 预解析生效路径前缀
        self._scoped_paths: list[str] = [p for p in settings.IP_WHITELIST_PATHS if p]

    def _parse_whitelist(self, whitelist: list[str]) -> None:
        """解析白名单配置，区分单 IP 与 CIDR 网络。"""
        import ipaddress

        for entry in whitelist:
            entry = entry.strip()
            if not entry:
                continue
            try:
                if "/" in entry:
                    self._networks.append(ipaddress.ip_network(entry, strict=False))
                else:
                    self._exact_ips.add(entry)
            except ValueError:
                logger.warning("IP 白名单条目格式无效，已忽略", entry=entry)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """IP 白名单检查。"""
        # 判断是否启用白名单
        whitelist_enabled = settings.IP_WHITELIST_ENABLED or bool(self._exact_ips or self._networks)
        if not whitelist_enabled:
            return await call_next(request)

        path = request.url.path
        # 豁免路径直接放行
        if any(path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)

        # 若配置了生效路径前缀，则仅对匹配路径启用白名单
        if self._scoped_paths and not any(path.startswith(prefix) for prefix in self._scoped_paths):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        if client_ip is None:
            logger.warning("无法获取客户端 IP，已拒绝请求", path=path)
            return JSONResponse(
                status_code=403,
                content={"detail": "访问被拒绝"},
            )

        if not self._is_allowed(client_ip):
            logger.warning(
                "IP 不在白名单中",
                client_ip=client_ip,
                path=path,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "访问被拒绝：IP 不在白名单中"},
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str | None:
        """获取客户端真实 IP。

        优先解析 ``X-Forwarded-For`` 请求头，其次使用 ``request.client.host``。
        """
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else None

    def _is_allowed(self, ip: str) -> bool:
        """检查 IP 是否在白名单中。"""
        # 单 IP 精确匹配
        if ip in self._exact_ips:
            return True

        # CIDR 网络匹配
        if self._networks:
            import ipaddress

            try:
                addr = ipaddress.ip_address(ip)
                for network in self._networks:
                    if addr in network:
                        return True
            except ValueError:
                return False

        return False


__all__ = ["IPWhitelistMiddleware"]
