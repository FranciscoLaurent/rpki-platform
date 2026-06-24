"""RIPE RIS（Routing Information Service）数据采集器。

通过 RIS Live WebSocket 实时订阅 BGP 公告与撤路事件。
当前为占位实现，接口完整，实际采集逻辑待实现。

参考文档：
- RIS Live: https://ris-live.ripe.net/
- RIS Live WebSocket: wss://ris-live.ripe.net/v1/ws/
"""

from __future__ import annotations

from typing import Any

from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services import bgp_parser

logger: BoundLogger = get_logger("app.ris_collector")

# RIS Live WebSocket 默认地址
DEFAULT_RIS_LIVE_URL = "wss://ris-live.ripe.net/v1/ws/"


class RIPERisCollector:
    """RIPE RIS Live 数据采集器。

    通过 WebSocket 连接 RIS Live 服务，实时订阅 BGP UPDATE 消息。
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """初始化 RIS 采集器。

        Args:
            config: 配置字典，支持以下键：
                - ``url``: RIS Live WebSocket URL（默认使用官方地址）
                - ``rrcs``: 订阅的 RRC 列表（如 ``[0, 1, 2]``）
                - ``prefixes``: 订阅的前缀列表
                - ``types``: 订阅的消息类型（如 ``["UPDATE"]``）
                - ``require``: 必须包含的字段
        """
        self._config = config or {}
        self._url: str = self._config.get("url", DEFAULT_RIS_LIVE_URL)
        self._rrcs: list[int] | None = self._config.get("rrcs")
        self._prefixes: list[str] | None = self._config.get("prefixes")
        self._types: list[str] = self._config.get("types", ["UPDATE"])
        self._require: list[str] | None = self._config.get("require")

        self._websocket: Any = None
        self._running: bool = False
        self._subscribed: bool = False

    async def connect(self) -> None:
        """连接 RIS Live WebSocket 服务。

        使用 ``websockets`` 库建立连接。
        连接成功后自动发送订阅请求。

        Raises:
            RuntimeError: 连接失败
        """
        # TODO: 实际实现需引入 websockets 库
        # import websockets
        # self._websocket = await websockets.connect(self._url)
        logger.info("连接 RIS Live WebSocket", url=self._url)
        self._running = True
        # 占位：实际连接逻辑待实现
        raise NotImplementedError("RIS Live WebSocket 连接尚未实现，请引入 websockets 库并完成实现")

    async def subscribe(self, prefixes: list[str] | None = None) -> None:
        """订阅特定前缀的 BGP 公告。

        向 RIS Live 发送订阅请求，指定过滤条件。

        Args:
            prefixes: 要订阅的前缀列表，为 None 则使用初始化时配置的前缀
        """
        if prefixes is not None:
            self._prefixes = prefixes

        subscription: dict[str, Any] = {
            "type": "ris_subscribe",
            "data": {
                "type": self._types,
            },
        }

        if self._rrcs is not None:
            subscription["data"]["rrcs"] = self._rrcs
        if self._prefixes is not None:
            subscription["data"]["prefixes"] = self._prefixes
        if self._require is not None:
            subscription["data"]["require"] = self._require

        # TODO: 实际发送订阅消息
        # if self._websocket is not None:
        #     await self._websocket.send(json.dumps(subscription))

        logger.info(
            "订阅 RIS Live 消息",
            rrcs=self._rrcs,
            prefixes=self._prefixes,
            types=self._types,
        )
        self._subscribed = True

    async def consume(self) -> Any:
        """消费 RIS Live 消息并解析。

        持续从 WebSocket 接收消息，解析 BGP UPDATE 并返回公告与撤路信息。

        Yields:
            解析后的消息字典，包含 ``announcements`` 与 ``withdraws`` 列表
        """
        if not self._running or self._websocket is None:
            raise RuntimeError("采集器未启动，请先调用 connect()")

        # TODO: 实际消费逻辑
        # while self._running:
        #     raw_message = await self._websocket.recv()
        #     message = json.loads(raw_message)
        #     if message.get("type") != "ris_message":
        #         continue
        #     parsed = self._parse_ris_message(message["data"])
        #     if parsed:
        #         yield parsed

        logger.info("开始消费 RIS Live 消息")
        raise NotImplementedError("RIS Live 消息消费尚未实现")

    def _parse_ris_message(self, data: dict[str, Any]) -> dict[str, Any]:
        """解析 RIS Live 消息。

        RIS Live 消息格式参考：https://ris-live.ripe.net/manual/

        Args:
            data: RIS Live 消息数据

        Returns:
            解析后的字典，包含 ``announcements`` 与 ``withdraws`` 列表
        """
        result: dict[str, Any] = {"announcements": [], "withdraws": []}

        # 提取基础信息
        timestamp = data.get("timestamp")
        peer = data.get("peer")
        peer_asn = data.get("peer_asn")
        rrc = data.get("rrc")

        # 解析路径属性
        raw_attributes = data.get("path") or {}
        if isinstance(raw_attributes, list):
            # RIS Live 中 path 字段为 AS 列表
            raw_attributes = {"as_path": raw_attributes}

        attributes = bgp_parser.parse_bgp_attributes(raw_attributes)
        if peer_asn is not None and "as_path" not in attributes:
            # 使用 peer_asn 作为 origin_as 的回退
            attributes["as_path"] = [int(peer_asn)]

        # 解析公告
        announcements = data.get("announcements", [])
        if isinstance(announcements, list):
            for ann in announcements:
                prefixes = ann.get("prefixes", [])
                for prefix in prefixes:
                    family, length, _ = bgp_parser.parse_prefix(prefix)
                    result["announcements"].append(
                        {
                            "prefix": bgp_parser.normalize_prefix(prefix),
                            "prefix_family": family,
                            "prefix_length": length,
                            "origin_as": (
                                attributes["as_path"][-1] if attributes.get("as_path") else None
                            ),
                            "as_path": attributes.get("as_path", []),
                            "next_hop": ann.get("next_hop") or attributes.get("next_hop"),
                            "communities": attributes.get("communities", []),
                            "large_communities": attributes.get("large_communities", []),
                            "med": attributes.get("med"),
                            "local_pref": attributes.get("local_pref"),
                            "timestamp": timestamp,
                            "peer": peer,
                            "rrc": rrc,
                            "address_family": family,
                        }
                    )

        # 解析撤路
        withdraws = data.get("withdraws", [])
        if isinstance(withdraws, list):
            for prefix in withdraws:
                if isinstance(prefix, str):
                    family, length, _ = bgp_parser.parse_prefix(prefix)
                    result["withdraws"].append(
                        {
                            "prefix": bgp_parser.normalize_prefix(prefix),
                            "prefix_family": family,
                            "prefix_length": length,
                            "timestamp": timestamp,
                            "peer": peer,
                            "rrc": rrc,
                        }
                    )

        return result

    async def disconnect(self) -> None:
        """断开 RIS Live WebSocket 连接。"""
        self._running = False
        self._subscribed = False

        # TODO: 实际断开连接
        # if self._websocket is not None:
        #     await self._websocket.close()
        #     self._websocket = None

        logger.info("断开 RIS Live WebSocket 连接")

    @property
    def is_running(self) -> bool:
        """采集器是否正在运行。"""
        return self._running

    @property
    def is_subscribed(self) -> bool:
        """是否已订阅。"""
        return self._subscribed
