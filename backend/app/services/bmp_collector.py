"""BMP（BGP Monitoring Protocol）采集器。

实现 BMP 服务器，接收来自网络设备的 BMP 消息流。
BMP 协议定义于 RFC 7854，用于实时监控 BGP 会话状态与路由信息。

参考文档：
- RFC 7854: BMP 协议规范
- RFC 8671: BMP 支持 Adj-RIB-Out
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any

from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services import bgp_parser

logger: BoundLogger = get_logger("app.bmp_collector")

# BMP 默认监听端口
DEFAULT_BMP_PORT = 1790

# BMP 消息类型（RFC 7854）
BMP_MSG_ROUTE_MONITORING = 0
BMP_MSG_STATISTICS_REPORT = 1
BMP_MSG_PEER_DOWN = 2
BMP_MSG_PEER_UP = 3
BMP_MSG_INITIATION = 4
BMP_MSG_TERMINATION = 5
BMP_MSG_ROUTE_MIRRORING = 6

# BMP 消息类型名称
BMP_MSG_TYPE_NAMES = {
    BMP_MSG_ROUTE_MONITORING: "route_monitoring",
    BMP_MSG_STATISTICS_REPORT: "statistics_report",
    BMP_MSG_PEER_DOWN: "peer_down",
    BMP_MSG_PEER_UP: "peer_up",
    BMP_MSG_INITIATION: "initiation",
    BMP_MSG_TERMINATION: "termination",
    BMP_MSG_ROUTE_MIRRORING: "route_mirroring",
}


class BMPCollector:
    """BMP 采集器。

    启动 TCP 服务器监听来自网络设备的 BMP 消息流，
    解析 BMP 消息并提取 BGP UPDATE 信息。
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """初始化 BMP 采集器。

        Args:
            config: 配置字典，支持以下键：
                - ``host``: 监听地址（默认 ``0.0.0.0``）
                - ``port``: 监听端口（默认 1790）
                - ``max_connections``: 最大连接数
        """
        self._config = config or {}
        self._host: str = self._config.get("host", "0.0.0.0")
        self._port: int = self._config.get("port", DEFAULT_BMP_PORT)
        self._max_connections: int = self._config.get("max_connections", 100)

        self._server: asyncio.AbstractServer | None = None
        self._running: bool = False
        self._connections: dict[str, asyncio.StreamWriter] = {}

    async def start_server(self) -> None:
        """启动 BMP TCP 服务器。

        监听指定端口，接收来自网络设备的 BMP 连接。

        Raises:
            RuntimeError: 服务器启动失败
        """
        # TODO: 实际实现
        # self._server = await asyncio.start_server(
        #     self._handle_connection,
        #     host=self._host,
        #     port=self._port,
        # )
        # self._running = True
        # logger.info("BMP 服务器已启动", host=self._host, port=self._port)

        logger.info("启动 BMP 服务器", host=self._host, port=self._port)
        self._running = True
        raise NotImplementedError("BMP 服务器启动尚未实现")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理新的 BMP 连接。

        Args:
            reader: 流读取器
            writer: 流写入器
        """
        peer_addr = writer.get_extra_info("peername")
        peer_key = f"{peer_addr[0]}:{peer_addr[1]}" if peer_addr else "unknown"
        self._connections[peer_key] = writer

        logger.info("接受 BMP 连接", peer=peer_key)

        try:
            while self._running:
                # 读取 BMP 消息头（公共头为 6 字节）
                header = await reader.readexactly(6)
                version, msg_length, msg_type = struct.unpack("!BIB", header)

                if version != 3:
                    logger.warning(
                        "不支持的 BMP 版本",
                        peer=peer_key,
                        version=version,
                    )
                    break

                # 读取消息体
                body_length = msg_length - 6
                if body_length > 0:
                    body = await reader.readexactly(body_length)
                else:
                    body = b""

                # 解析 BMP 消息
                await self.handle_bmp_message(
                    {
                        "peer": peer_key,
                        "version": version,
                        "type": msg_type,
                        "type_name": BMP_MSG_TYPE_NAMES.get(
                            msg_type, f"unknown({msg_type})"
                        ),
                        "body": body,
                    }
                )
        except asyncio.IncompleteReadError:
            logger.info("BMP 连接关闭", peer=peer_key)
        except Exception as e:
            logger.error("BMP 连接异常", peer=peer_key, error=str(e))
        finally:
            self._connections.pop(peer_key, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def handle_bmp_message(self, message: dict[str, Any]) -> None:
        """处理 BMP 消息。

        根据 BMP 消息类型分发处理。

        Args:
            message: BMP 消息字典，包含 ``type``、``body`` 等字段
        """
        msg_type = message.get("type")
        peer = message.get("peer")

        if msg_type == BMP_MSG_ROUTE_MONITORING:
            # 路由监控消息，包含 BGP UPDATE
            parsed = self.parse_bmp_message(message.get("body", b""))
            if parsed:
                logger.debug(
                    "解析 BMP 路由监控消息",
                    peer=peer,
                    announcements=len(parsed.get("announcements", [])),
                    withdraws=len(parsed.get("withdraws", [])),
                )
        elif msg_type == BMP_MSG_PEER_UP:
            logger.info("BGP 邻居建立", peer=peer)
        elif msg_type == BMP_MSG_PEER_DOWN:
            logger.info("BGP 邻居断开", peer=peer)
        elif msg_type == BMP_MSG_INITIATION:
            logger.info("BMP 会话初始化", peer=peer)
        elif msg_type == BMP_MSG_TERMINATION:
            logger.info("BMP 会话终止", peer=peer)
        else:
            logger.debug("未处理的 BMP 消息类型", type=msg_type, peer=peer)

    def parse_bmp_message(self, data: bytes) -> dict[str, Any]:
        """解析 BMP 消息体。

        BMP 路由监控消息包含完整的 BGP UPDATE 消息。
        此方法提取 BGP UPDATE 并调用 BGP 解析器解析。

        BMP 消息体结构（路由监控消息）：
        - Per-Peer Header (42 字节)
        - BGP Update 消息

        Args:
            data: BMP 消息体字节

        Returns:
            解析后的字典，包含 ``announcements`` 与 ``withdraws`` 列表
        """
        if not data or len(data) < 42:
            return {"announcements": [], "withdraws": []}

        # 跳过 Per-Peer Header（42 字节）
        # Per-Peer Header 结构：
        # - Peer Type (1 字节)
        # - Peer Flags (1 字节)
        # - Peer Distinguisher (8 字节)
        # - Peer Address (16 字节)
        # - Peer AS (4 字节)
        # - Peer BGP ID (4 字节)
        # - Timestamp (8 字节)
        peer_header = data[:42]
        bgp_data = data[42:]

        # 解析 Peer 信息
        try:
            peer_as = struct.unpack("!I", peer_header[10:14])[0]
            peer_bgp_id = peer_header[14:18]
            peer_address = peer_header[2:18]
        except struct.error:
            peer_as = None

        # BGP UPDATE 消息结构：
        # - Withdrawn Routes Length (2 字节)
        # - Withdrawn Routes (变长)
        # - Total Path Attribute Length (2 字节)
        # - Path Attributes (变长)
        # - NLRI (变长)
        if len(bgp_data) < 4:
            return {"announcements": [], "withdraws": []}

        try:
            withdrawn_length = struct.unpack("!H", bgp_data[0:2])[0]
            offset = 2

            # 解析撤销路由
            withdrawn_routes = bgp_data[offset : offset + withdrawn_length]
            offset += withdrawn_length

            # 解析路径属性
            path_attr_length = struct.unpack(
                "!H", bgp_data[offset : offset + 2]
            )[0]
            offset += 2
            path_attributes = bgp_data[offset : offset + path_attr_length]
            offset += path_attr_length

            # NLRI 为剩余部分
            nlri = bgp_data[offset:]

            # 解析路径属性
            attributes = bgp_parser.parse_bgp_attributes(path_attributes)

            # 构造 BGP UPDATE 字典并解析
            update_data = {
                "withdrawn_routes": _extract_prefixes_from_bytes(withdrawn_routes),
                "nlri": _extract_prefixes_from_bytes(nlri),
                "attributes": attributes,
                "origin_as": (
                    attributes.get("as_path", [None])[-1]
                    if attributes.get("as_path")
                    else peer_as
                ),
            }

            return bgp_parser.parse_bgp_update(update_data)
        except Exception as e:
            logger.warning("解析 BMP 消息失败", error=str(e))
            return {"announcements": [], "withdraws": []}

    async def stop_server(self) -> None:
        """停止 BMP 服务器。"""
        self._running = False

        # 关闭所有客户端连接
        for peer_key, writer in list(self._connections.items()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._connections.clear()

        # 关闭服务器
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("BMP 服务器已停止")

    @property
    def is_running(self) -> bool:
        """服务器是否正在运行。"""
        return self._running

    @property
    def active_connections(self) -> int:
        """当前活跃连接数。"""
        return len(self._connections)


def _extract_prefixes_from_bytes(data: bytes) -> list[str]:
    """从 NLRI 字节流中提取前缀列表。

    NLRI 格式：
    - Prefix Length (1 字节)
    - Prefix (变长，按长度计算)

    Args:
        data: NLRI 字节流

    Returns:
        前缀字符串列表
    """
    import ipaddress

    prefixes: list[str] = []
    offset = 0

    while offset < len(data):
        prefix_length = data[offset]
        offset += 1

        # 计算前缀字节数
        prefix_bytes = (prefix_length + 7) // 8
        if offset + prefix_bytes > len(data):
            break

        prefix_data = data[offset : offset + prefix_bytes]
        offset += prefix_bytes

        # 补全为 4 字节（IPv4）或 16 字节（IPv6）
        if prefix_bytes <= 4:
            # IPv4
            padded = prefix_data + b"\x00" * (4 - prefix_bytes)
            addr = ipaddress.IPv4Address(padded)
            prefixes.append(f"{addr}/{prefix_length}")
        else:
            # IPv6
            padded = prefix_data + b"\x00" * (16 - prefix_bytes)
            addr = ipaddress.IPv6Address(padded)
            prefixes.append(f"{addr}/{prefix_length}")

    return prefixes
