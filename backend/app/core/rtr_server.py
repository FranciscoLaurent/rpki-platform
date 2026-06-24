"""RPKI-RTR TCP 服务端引擎。

基于 asyncio 实现 RPKI-RTR 协议（RFC 8210）服务端，支持多客户端
并发连接、白名单访问控制与 mTLS（占位）。每个 RTR 服务实例对应
一个 :class:`RTRServerEngine` 实例。
"""

from __future__ import annotations

import asyncio
import ipaddress
import struct
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.core.rtr_protocol import RTRProtocol

logger = get_logger("app.rtr_server")


class RTRClientInfo:
    """RTR 客户端连接信息。

    封装单个客户端连接的读写流、地址与同步状态。
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        client_ip: str,
        client_port: int,
    ) -> None:
        """初始化客户端信息。

        Args:
            reader: 异步读流
            writer: 异步写流
            client_ip: 客户端 IP
            client_port: 客户端端口
        """
        self.reader = reader
        self.writer = writer
        self.client_ip = client_ip
        self.client_port = client_port
        self.connected_at = datetime.now(UTC)
        self.last_activity_at = datetime.now(UTC)
        self.last_serial: int | None = None
        self.client_version: int = RTRProtocol.DEFAULT_VERSION
        self.session_state: str = "established"
        self.bytes_sent = 0
        self.bytes_received = 0

    def update_activity(self) -> None:
        """更新最近活动时间。"""
        self.last_activity_at = datetime.now(UTC)

    def __repr__(self) -> str:
        return (
            f"<RTRClientInfo(ip={self.client_ip}, port={self.client_port}, "
            f"state={self.session_state})>"
        )


class RTRServerEngine:
    """RTR TCP 服务端引擎。

    一个引擎实例负责监听一个 (host, port) 端口，处理多个客户端连接，
    维护当前 VRP 数据与序列号，并向客户端推送更新通知。

    典型用法::

        engine = RTRServerEngine(host="0.0.0.0", port=8282, session_id=1)
        engine.update_vrps(vrp_list, serial=10)
        await engine.start()
        # ...
        await engine.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8282,
        session_id: int = 1,
        whitelist: list[str] | None = None,
        mtls_enabled: bool = False,
        version: int = RTRProtocol.DEFAULT_VERSION,
    ) -> None:
        """初始化 RTR 服务端引擎。

        Args:
            host: 监听地址
            port: 监听端口
            session_id: RTR Session ID
            whitelist: 允许连接的客户端 IP 列表，None 或空表示不限制
            mtls_enabled: 是否启用 mTLS（占位，当前未实际校验）
            version: RTR 协议版本
        """
        self.host = host
        self.port = port
        self.session_id = session_id
        self.whitelist = list(whitelist) if whitelist else []
        self.mtls_enabled = mtls_enabled
        self.version = version

        # 运行状态
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[RTRClientInfo] = set()
        self._lock = asyncio.Lock()

        # VRP 数据与序列号
        self._vrps: list[dict[str, Any]] = []
        self._current_serial: int = 0
        self._started_at: datetime | None = None
        self._last_error: str | None = None
        self._running = False

    # ──────────────────────────────────────────────
    # 属性
    # ──────────────────────────────────────────────

    @property
    def running(self) -> bool:
        """服务是否正在运行。"""
        return self._running

    @property
    def current_serial(self) -> int:
        """当前序列号。"""
        return self._current_serial

    @property
    def vrps_count(self) -> int:
        """当前 VRP 数量。"""
        return len(self._vrps)

    @property
    def connected_clients_count(self) -> int:
        """当前连接客户端数。"""
        return len(self._clients)

    @property
    def uptime(self) -> int:
        """运行时长（秒）。"""
        if self._started_at is None:
            return 0
        return int((datetime.now(UTC) - self._started_at).total_seconds())

    @property
    def last_error(self) -> str | None:
        """最近一次错误信息。"""
        return self._last_error

    # ──────────────────────────────────────────────
    # VRP 数据管理
    # ──────────────────────────────────────────────

    def update_vrps(
        self,
        vrps: list[dict[str, Any]],
        serial: int | None = None,
    ) -> int:
        """更新服务端 VRP 数据。

        Args:
            vrps: 新的 VRP 列表，每个 VRP 字典应包含 prefix、prefix_length、
                origin_as，可选 max_length
            serial: 新的序列号，None 时自动递增

        Returns:
            更新后的序列号
        """
        self._vrps = list(vrps)
        if serial is not None:
            self._current_serial = serial
        else:
            self._current_serial += 1
        logger.info(
            "RTR 服务端 VRP 数据已更新",
            host=self.host,
            port=self.port,
            vrps_count=len(self._vrps),
            serial=self._current_serial,
        )
        return self._current_serial

    def get_vrps(self) -> list[dict[str, Any]]:
        """获取当前 VRP 列表（深拷贝）。"""
        return list(self._vrps)

    # ──────────────────────────────────────────────
    # 服务生命周期
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """启动 TCP 服务器。

        Raises:
            RuntimeError: 服务器已在运行
            OSError: 端口被占用等
        """
        if self._running:
            raise RuntimeError("RTR 服务端已在运行")
        self._server = await asyncio.start_server(
            self._handle_client_wrapper,
            host=self.host,
            port=self.port,
        )
        self._running = True
        self._started_at = datetime.now(UTC)
        self._last_error = None
        logger.info(
            "RTR 服务端已启动",
            host=self.host,
            port=self.port,
            session_id=self.session_id,
        )

    async def stop(self) -> None:
        """停止 TCP 服务器并关闭所有客户端连接。"""
        if not self._running:
            return
        self._running = False

        # 关闭所有客户端连接
        async with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.writer.close()
                await client.writer.wait_closed()
            except Exception as e:
                logger.warning(
                    "关闭客户端连接异常",
                    client_ip=client.client_ip,
                    error=str(e),
                )

        # 关闭服务器
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception as e:
                logger.warning("关闭服务器异常", error=str(e))
            self._server = None

        logger.info("RTR 服务端已停止", host=self.host, port=self.port)

    # ──────────────────────────────────────────────
    # 客户端连接管理
    # ──────────────────────────────────────────────

    async def _handle_client_wrapper(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """客户端连接处理包装器。

        提取客户端 IP/端口，执行白名单与 mTLS 检查后委托给
        :meth:`handle_client`。
        """
        peername = writer.get_extra_info("peername")
        client_ip = peername[0] if peername else "unknown"
        client_port = peername[1] if peername and len(peername) > 1 else 0

        # 白名单检查
        if not self.check_whitelist(client_ip):
            logger.warning(
                "客户端 IP 不在白名单，拒绝连接",
                client_ip=client_ip,
                server=f"{self.host}:{self.port}",
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return

        # mTLS 检查（占位）
        if self.mtls_enabled:
            peercert = writer.get_extra_info("peercert")
            if not self.check_mtls(peercert):
                logger.warning(
                    "mTLS 校验失败，拒绝连接",
                    client_ip=client_ip,
                    server=f"{self.host}:{self.port}",
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return

        client = RTRClientInfo(reader, writer, client_ip, client_port)
        await self.handle_client(client)

    async def handle_client(self, client: RTRClientInfo) -> None:
        """处理单个客户端连接。

        将客户端加入连接集合，循环读取并处理 PDU，直到连接关闭。

        Args:
            client: 客户端信息对象
        """
        await self.add_client(client)
        logger.info(
            "RTR 客户端已连接",
            client_ip=client.client_ip,
            client_port=client.client_port,
            server=f"{self.host}:{self.port}",
        )
        try:
            while self._running:
                try:
                    # 先读取 8 字节头部
                    header = await client.reader.readexactly(RTRProtocol.HEADER_LENGTH)
                except asyncio.IncompleteReadError:
                    # 客户端正常关闭连接
                    break
                except ConnectionResetError:
                    break

                # 解析头部获取完整 PDU 长度
                _, _, _, length = struct.unpack("!BBHI", header)
                if length < RTRProtocol.HEADER_LENGTH:
                    logger.warning(
                        "客户端发送非法 PDU 长度",
                        client_ip=client.client_ip,
                        length=length,
                    )
                    break

                # 读取剩余部分
                body_length = length - RTRProtocol.HEADER_LENGTH
                if body_length > 0:
                    try:
                        body = await client.reader.readexactly(body_length)
                    except asyncio.IncompleteReadError:
                        break
                else:
                    body = b""

                full_pdu = header + body
                client.bytes_received += len(full_pdu)
                client.update_activity()

                try:
                    await self.process_query(full_pdu, client)
                except Exception as e:
                    logger.exception(
                        "处理客户端查询异常",
                        client_ip=client.client_ip,
                        error=str(e),
                    )
                    # 发送错误报告
                    error_pdu = RTRProtocol.encode_error_report(
                        RTRProtocol.ERROR_INTERNAL_ERROR,
                        f"内部错误: {e}",
                        erroneous_pdu=full_pdu,
                        session_id=self.session_id,
                        version=client.client_version,
                    )
                    try:
                        client.writer.write(error_pdu)
                        await client.writer.drain()
                        client.bytes_sent += len(error_pdu)
                    except Exception:
                        break
        finally:
            await self.remove_client(client)
            try:
                client.writer.close()
                await client.writer.wait_closed()
            except Exception:
                pass
            logger.info(
                "RTR 客户端已断开",
                client_ip=client.client_ip,
                client_port=client.client_port,
            )

    async def process_query(self, query: bytes, client: RTRClientInfo) -> None:
        """处理客户端查询 PDU。

        根据 PDU 类型分发处理：
        - SERIAL_QUERY：发送增量更新（当前实现发送全量）
        - RESET_QUERY：发送全量更新
        - 其他：发送错误报告

        Args:
            query: 完整 PDU 字节流
            client: 客户端信息对象
        """
        try:
            decoded = RTRProtocol.decode_pdu(query)
        except ValueError as e:
            logger.warning(
                "解码客户端 PDU 失败",
                client_ip=client.client_ip,
                error=str(e),
            )
            error_pdu = RTRProtocol.encode_error_report(
                RTRProtocol.ERROR_CORRUPT_DATA,
                f"PDU 解码失败: {e}",
                erroneous_pdu=query,
                session_id=self.session_id,
                version=client.client_version,
            )
            client.writer.write(error_pdu)
            await client.writer.drain()
            client.bytes_sent += len(error_pdu)
            return

        # 更新客户端协议版本
        client.client_version = decoded["version"]
        pdu_type = decoded["pdu_type"]
        payload = decoded["payload"]

        if pdu_type == RTRProtocol.PDU_SERIAL_QUERY:
            # 序列号查询：解析客户端最后已知序列号
            try:
                serial_info = RTRProtocol.decode_serial_pdu(payload)
                client.last_serial = serial_info["serial_number"]
            except ValueError:
                pass
            await self.send_vrps(
                client.writer,
                self._vrps,
                self._current_serial,
                client=client,
            )
            client.last_serial = self._current_serial
        elif pdu_type == RTRProtocol.PDU_RESET_QUERY:
            # 全量查询
            await self.send_vrps(
                client.writer,
                self._vrps,
                self._current_serial,
                client=client,
            )
            client.last_serial = self._current_serial
        else:
            # 不支持的 PDU 类型
            logger.warning(
                "收到不支持的 PDU 类型",
                client_ip=client.client_ip,
                pdu_type=pdu_type,
            )
            error_pdu = RTRProtocol.encode_error_report(
                RTRProtocol.ERROR_UNSUPPORTED_PDU_TYPE,
                f"不支持的 PDU 类型: {pdu_type}",
                erroneous_pdu=query,
                session_id=self.session_id,
                version=client.client_version,
            )
            client.writer.write(error_pdu)
            await client.writer.drain()
            client.bytes_sent += len(error_pdu)

    async def send_vrps(
        self,
        writer: asyncio.StreamWriter,
        vrps: list[dict[str, Any]],
        serial: int,
        client: RTRClientInfo | None = None,
    ) -> None:
        """向客户端发送 VRP 数据。

        发送顺序：Cache Response → IPv4/IPv6 Prefix PDUs → End of Data。

        Args:
            writer: 客户端写流
            vrps: VRP 字典列表
            serial: 当前序列号
            client: 客户端信息对象（用于统计）
        """
        # 1. 发送 Cache Response
        cache_response = RTRProtocol.encode_cache_response(
            session_id=self.session_id, version=self.version
        )
        writer.write(cache_response)
        sent = len(cache_response)

        # 2. 发送 VRP 数据
        vrps_data = RTRProtocol.encode_vrps(
            vrps,
            session_id=self.session_id,
            version=self.version,
        )
        if vrps_data:
            writer.write(vrps_data)
            sent += len(vrps_data)

        # 3. 发送 End of Data
        end_of_data = RTRProtocol.encode_end_of_data(
            serial_number=serial,
            session_id=self.session_id,
            version=self.version,
        )
        writer.write(end_of_data)
        sent += len(end_of_data)

        await writer.drain()

        if client is not None:
            client.bytes_sent += sent
            client.update_activity()

        logger.info(
            "已向客户端发送 VRP 数据",
            vrps_count=len(vrps),
            serial=serial,
            bytes=sent,
        )

    async def notify_clients(self, serial: int) -> None:
        """向所有连接的客户端发送 Serial Notify。

        通知客户端序列号已更新，客户端应主动发起 Serial Query 获取增量。

        Args:
            serial: 新的序列号
        """
        async with self._lock:
            clients = list(self._clients)

        notify_pdu = RTRProtocol.encode_serial_notify(
            serial_number=serial,
            session_id=self.session_id,
            version=self.version,
        )

        for client in clients:
            try:
                client.writer.write(notify_pdu)
                await client.writer.drain()
                client.bytes_sent += len(notify_pdu)
                client.update_activity()
            except Exception as e:
                logger.warning(
                    "向客户端发送 Serial Notify 失败",
                    client_ip=client.client_ip,
                    error=str(e),
                )

        logger.info(
            "已通知所有客户端序列号更新",
            serial=serial,
            client_count=len(clients),
        )

    async def add_client(self, client: RTRClientInfo) -> None:
        """添加客户端到连接集合。

        Args:
            client: 客户端信息对象
        """
        async with self._lock:
            self._clients.add(client)

    async def remove_client(self, client: RTRClientInfo) -> None:
        """从连接集合移除客户端。

        Args:
            client: 客户端信息对象
        """
        async with self._lock:
            self._clients.discard(client)

    def get_connected_clients(self) -> list[dict[str, Any]]:
        """获取所有连接的客户端信息列表。

        Returns:
            客户端信息字典列表，包含 ip、port、connected_at、last_serial 等
        """
        return [
            {
                "client_ip": c.client_ip,
                "client_port": c.client_port,
                "connected_at": c.connected_at.isoformat(),
                "last_activity_at": c.last_activity_at.isoformat(),
                "last_serial": c.last_serial,
                "client_version": c.client_version,
                "session_state": c.session_state,
                "bytes_sent": c.bytes_sent,
                "bytes_received": c.bytes_received,
            }
            for c in self._clients
        ]

    def get_client_infos(self) -> list[RTRClientInfo]:
        """获取所有连接的客户端信息对象列表。

        Returns:
            客户端信息对象列表（浅拷贝）
        """
        return list(self._clients)

    # ──────────────────────────────────────────────
    # 访问控制
    # ──────────────────────────────────────────────

    def check_whitelist(self, client_ip: str) -> bool:
        """检查客户端 IP 是否在白名单中。

        支持单 IP 与 CIDR 网段匹配。白名单为空时允许所有连接。

        Args:
            client_ip: 客户端 IP 地址

        Returns:
            是否允许连接
        """
        if not self.whitelist:
            return True
        try:
            ip = ipaddress.ip_address(client_ip)
        except ValueError:
            return False

        for entry in self.whitelist:
            try:
                if "/" in entry:
                    network = ipaddress.ip_network(entry, strict=False)
                    if ip in network:
                        return True
                else:
                    if ip == ipaddress.ip_address(entry):
                        return True
            except ValueError:
                continue
        return False

    def check_mtls(self, cert: Any) -> bool:
        """检查客户端 mTLS 证书。

        当前为占位实现，始终返回 True。实际部署时应校验证书链、
        主题、有效期与撤销状态。

        Args:
            cert: 客户端证书对象（来自 SSLContext）

        Returns:
            是否通过校验
        """
        # TODO: 实现 mTLS 证书校验
        # 1. 校验证书链
        # 2. 校验主题（CN 或 SAN）
        # 3. 校验有效期
        # 4. 校验撤销状态（CRL/OCSP）
        if not self.mtls_enabled:
            return True
        if cert is None:
            return False
        return True


__all__ = ["RTRClientInfo", "RTRServerEngine"]
