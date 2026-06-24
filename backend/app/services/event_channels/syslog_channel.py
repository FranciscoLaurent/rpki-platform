"""Syslog 推送通道（RFC 5424）。

通过 UDP/TCP 将事件以 RFC 5424 格式推送到 Syslog 服务器。
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from datetime import UTC, datetime
from typing import Any

from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services.event_channels.base import BaseChannel, ChannelResult

logger: BoundLogger = get_logger("app.event_channels.syslog")


# Syslog 设施码（local0-local7 为 16-23）
SYSLOG_FACILITIES = {
    "kern": 0,
    "user": 1,
    "mail": 2,
    "daemon": 3,
    "auth": 4,
    "syslog": 5,
    "local0": 16,
    "local1": 17,
    "local2": 18,
    "local3": 19,
    "local4": 20,
    "local5": 21,
    "local6": 22,
    "local7": 23,
}

# 严重等级到 Syslog 严重性的映射
SEVERITY_TO_SYSLOG = {
    "P0": 1,  # Alert
    "P1": 2,  # Critical
    "P2": 3,  # Error
    "P3": 4,  # Warning
    "P4": 5,  # Notice
}


class SyslogChannel(BaseChannel):
    """Syslog 推送通道（RFC 5424）。

    支持以下连接参数：
    - ``host``: Syslog 服务器地址（必填）
    - ``port``: 端口（默认 514）
    - ``protocol``: 协议（``udp`` 或 ``tcp``，默认 udp）
    - ``facility``: 设施码（默认 local0）
    - ``hostname``: 主机名（默认本机名）
    - ``app_name``: 应用名（默认 rpki-platform）
    - ``timeout``: 超时（秒，默认 5）
    """

    async def send(
        self,
        target: str,
        payload: dict[str, Any],
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """发送事件到 Syslog 服务器。

        ``target`` 参数在此通道中可留空，实际地址从 ``connection_params`` 读取。
        """
        connection_params = connection_params or {}
        extra_config = extra_config or {}

        host = connection_params.get("host") or target.split(":")[0] if target else None
        if not host:
            return ChannelResult(
                success=False,
                error_message="Syslog 主机地址未配置",
            )
        port = int(connection_params.get("port", 514))
        protocol = connection_params.get("protocol", "udp").lower()
        facility = connection_params.get("facility", "local0")
        hostname = connection_params.get("hostname", socket.gethostname())
        app_name = connection_params.get("app_name", "rpki-platform")
        timeout = float(connection_params.get("timeout", 5))

        # 计算 PRI
        facility_code = SYSLOG_FACILITIES.get(facility, 16)
        severity = payload.get("severity", "P3")
        syslog_severity = SEVERITY_TO_SYSLOG.get(severity, 4)
        pri = facility_code * 8 + syslog_severity

        # 构造 RFC 5424 消息
        message = self._format_message(
            pri=pri,
            hostname=hostname,
            app_name=app_name,
            payload=payload,
            extra_config=extra_config,
        )

        start = time.monotonic()
        try:
            if protocol == "tcp":
                await self._send_tcp(host, port, message, timeout)
            else:
                await self._send_udp(host, port, message, timeout)

            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "Syslog 推送成功",
                host=host,
                port=port,
                protocol=protocol,
                latency_ms=latency_ms,
            )
            return ChannelResult(
                success=True,
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Syslog 推送失败",
                host=host,
                port=port,
                error=str(e),
            )
            return ChannelResult(
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def test_connection(
        self,
        target: str,
        connection_params: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> ChannelResult:
        """测试 Syslog 连接（发送测试消息）。"""
        connection_params = connection_params or {}
        test_payload = {
            "event_type": "syslog_test",
            "severity": "P4",
            "message": "Syslog connection test",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return await self.send(
            target=target,
            payload=test_payload,
            connection_params=connection_params,
            auth_config=auth_config,
            extra_config=extra_config,
        )

    def _format_message(
        self,
        pri: int,
        hostname: str,
        app_name: str,
        payload: dict[str, Any],
        extra_config: dict[str, Any],
    ) -> str:
        """构造 RFC 5424 格式的 Syslog 消息。

        格式：``<PRI>VERSION TIMESTAMP HOSTNAME APP_NAME PROCID MSGID STRUCTURED-DATA MSG``
        """
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        procid = str(payload.get("resource_id", "-"))
        msgid = payload.get("event_type", "-")

        # 结构化数据（SD-ID 为 rpki@1.0）
        sd_fields = []
        for key in ("severity", "prefix", "origin_as", "incident_id"):
            value = payload.get(key)
            if value is not None:
                escaped = str(value).replace('"', '\\"').replace("]", "\\]")
                sd_fields.append(f'{key}="{escaped}"')
        sd = f"[rpki@1.0 {' '.join(sd_fields)}]" if sd_fields else "-"

        # 消息体（JSON 格式）
        msg = json.dumps(payload, ensure_ascii=False, default=str)

        return f"<{pri}>1 {timestamp} {hostname} {app_name} {procid} {msgid} {sd} {msg}"

    async def _send_udp(self, host: str, port: int, message: str, timeout: float) -> None:
        """通过 UDP 发送 Syslog 消息。"""
        # TODO: 实际生产环境应使用连接池与异步 socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            data = message.encode("utf-8")
            if len(data) > 65507:
                # UDP 数据报过大，截断
                data = data[:65507]
            await asyncio.to_thread(sock.sendto, data, (host, port))
        finally:
            sock.close()

    async def _send_tcp(self, host: str, port: int, message: str, timeout: float) -> None:
        """通过 TCP 发送 Syslog 消息（octet-counting 帧）。"""
        # TODO: 实际生产环境应使用连接池
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        try:
            data = message.encode("utf-8")
            # Octet-counting 帧：``<length> <message>``
            frame = f"{len(data)} ".encode("ascii") + data
            writer.write(frame)
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
